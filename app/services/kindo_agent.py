"""Kindo AI Agent integration for patch analysis and rollout planning."""
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

KINDO_API_URL = "https://api.kindo.ai/v1/agents/runs"
POLL_INTERVAL = 2
DEFAULT_TIMEOUT = int(os.environ.get("APP_AGENT_POLL_TIMEOUT_SEC", "120"))


class KindoAgentError(Exception):
    pass


class KindoNotConfigured(KindoAgentError):
    pass


def _get_config():
    token = os.environ.get("KINDO_API_TOKEN")
    agent_id = os.environ.get("KINDO_AGENT_ID")
    if not token or not agent_id:
        missing = []
        if not token:
            missing.append("KINDO_API_TOKEN")
        if not agent_id:
            missing.append("KINDO_AGENT_ID")
        raise KindoNotConfigured(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "Configure them in Settings to enable AI analysis."
        )
    return token, agent_id


def call_agent(payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Call the Kindo enrichment agent and return parsed JSON result."""
    token, agent_id = _get_config()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "agent_id": agent_id,
        "inputs": [{"name": "request", "value": json.dumps(payload)}],
    }

    try:
        resp = requests.post(KINDO_API_URL, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Kindo agent start failed: %s", exc)
        raise KindoAgentError(f"Failed to start agent run: {exc}") from exc

    run_data = resp.json()
    run_id = run_data.get("id") or run_data.get("run_id")
    if not run_id:
        raise KindoAgentError("No run ID in agent response.")

    # Poll for completion
    status_url = f"{KINDO_API_URL}/{run_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            poll = requests.get(status_url, headers=headers, timeout=15)
            poll.raise_for_status()
            data = poll.json()
        except requests.RequestException as exc:
            logger.warning("Poll error (will retry): %s", exc)
            time.sleep(POLL_INTERVAL)
            continue

        status = data.get("status", "")
        if status in ("success", "completed"):
            return _parse_result(data)
        if status in ("failed", "error", "cancelled"):
            detail = data.get("error") or data.get("message") or "Unknown error"
            raise KindoAgentError(f"Agent run {status}: {detail}")

        time.sleep(POLL_INTERVAL)

    raise KindoAgentError(f"Agent run timed out after {timeout}s.")


def _parse_result(data: dict) -> dict:
    """Extract and parse the agent's JSON output."""
    output = data.get("output") or data.get("result") or data.get("response", "")
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        # Try to find JSON in the output
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown fences
            for marker in ("```json", "```"):
                if marker in output:
                    start = output.index(marker) + len(marker)
                    end = output.index("```", start) if "```" in output[start:] else len(output)
                    try:
                        return json.loads(output[start:end].strip())
                    except json.JSONDecodeError:
                        continue
            raise KindoAgentError(f"Could not parse agent output as JSON: {output[:500]}")
    raise KindoAgentError("Empty agent output.")


def is_configured() -> bool:
    """Check if the Kindo agent environment is properly configured."""
    try:
        _get_config()
        return True
    except KindoNotConfigured:
        return False


def analyze_patch(patch_data: dict, tenant_name: str = "") -> dict:
    """Analyze a patch for prioritization scoring."""
    payload = {
        "operation": "analyze",
        "entity_id": patch_data.get("patch_id_vendor", str(patch_data.get("id", ""))),
        "input_data": {
            "description": f"Analyze patch: {patch_data.get('title', '')}",
            "records": [patch_data],
            "context": {
                "organization": tenant_name,
                "policy": "default",
            },
        },
        "options": {
            "detail_level": "detailed",
            "include_recommendations": True,
            "return_confidence": True,
        },
    }
    return call_agent(payload)


def generate_rollout_plan(patches: list, assets: list, tenant_name: str = "") -> dict:
    """Generate a rollout plan for a set of patches and assets."""
    payload = {
        "operation": "generate",
        "entity_id": f"rollout-{int(time.time())}",
        "input_data": {
            "description": "Generate an optimal patch rollout plan",
            "records": [{"patches": patches, "assets": assets}],
            "context": {
                "organization": tenant_name,
                "policy": "minimize-downtime",
            },
        },
        "options": {
            "detail_level": "detailed",
            "include_recommendations": True,
            "return_confidence": True,
        },
    }
    return call_agent(payload)


def enrich_patch(patch_data: dict, tenant_name: str = "") -> dict:
    """Enrich a patch with additional context and threat intelligence."""
    payload = {
        "operation": "enrich",
        "entity_id": patch_data.get("patch_id_vendor", str(patch_data.get("id", ""))),
        "input_data": {
            "description": f"Enrich patch data: {patch_data.get('title', '')}",
            "records": [patch_data],
            "context": {
                "organization": tenant_name,
            },
        },
        "options": {
            "detail_level": "detailed",
            "include_recommendations": True,
            "return_confidence": True,
        },
    }
    return call_agent(payload)
