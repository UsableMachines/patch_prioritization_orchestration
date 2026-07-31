import logging
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Patch, Asset
from app.services.rbac import role_required, tenant_filter, log_audit
from app.services.kindo_agent import (
    analyze_patch, enrich_patch, is_configured,
    KindoAgentError, KindoNotConfigured,
)

logger = logging.getLogger(__name__)
patches_bp = Blueprint("patches", __name__, url_prefix="/patches")


@patches_bp.route("/")
@login_required
def list_patches():
    try:
        q = tenant_filter(Patch.query, Patch)
        status_filter = request.args.get("status")
        risk_filter = request.args.get("risk_level")
        if status_filter:
            q = q.filter(Patch.status == status_filter)
        if risk_filter:
            q = q.filter(Patch.risk_level == risk_filter)
        patches = q.order_by(Patch.priority_score.desc().nullslast(), Patch.created_at.desc()).all()
    except Exception as exc:
        logger.exception("list_patches: service error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("patches/list.html", patches=patches, agent_configured=is_configured())


@patches_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "analyst")
def create_patch():
    if request.method == "POST":
        try:
            cve_ids = request.form.get("cve_ids", "").strip()
            cvss = request.form.get("cvss_score", "")
            epss = request.form.get("epss_score", "")
            release = request.form.get("release_date", "")

            patch = Patch(
                title=request.form["title"].strip(),
                vendor=request.form.get("vendor", "").strip(),
                patch_id_vendor=request.form.get("patch_id_vendor", "").strip(),
                cve_ids=cve_ids,
                severity_vendor=request.form.get("severity_vendor", ""),
                cvss_score=float(cvss) if cvss else None,
                epss_score=float(epss) if epss else None,
                exploitability=request.form.get("exploitability", "unknown"),
                description=request.form.get("description", "").strip(),
                release_date=datetime.date.fromisoformat(release) if release else None,
                status="pending",
                tenant_id=current_user.tenant_id,
            )

            # Link affected assets
            asset_ids = request.form.getlist("asset_ids")
            if asset_ids:
                assets = tenant_filter(Asset.query, Asset).filter(Asset.id.in_(asset_ids)).all()
                patch.affected_assets = assets

            db.session.add(patch)
            db.session.commit()
            log_audit("patch_created", "Patch", patch.id, f"Created patch: {patch.title}")
        except Exception as exc:
            logger.exception("create_patch: error — %s", exc)
            db.session.rollback()
            flash("Failed to create patch.", "danger")
            return render_template("patches/form.html", patch=None, assets=[], agent_configured=is_configured()), 500

        flash("Patch created successfully.", "success")
        return redirect(url_for("patches.view_patch", patch_id=patch.id))

    try:
        assets = tenant_filter(Asset.query, Asset).order_by(Asset.name).all()
    except Exception as exc:
        logger.exception("create_patch GET: error — %s", exc)
        assets = []
    return render_template("patches/form.html", patch=None, assets=assets, agent_configured=is_configured())


@patches_bp.route("/<int:patch_id>")
@login_required
def view_patch(patch_id):
    try:
        patch = tenant_filter(Patch.query, Patch).filter_by(id=patch_id).first()
    except Exception as exc:
        logger.exception("view_patch: error — %s", exc)
        return render_template("errors/500.html"), 500

    if patch is None:
        flash("Patch not found.", "warning")
        return redirect(url_for("patches.list_patches"))

    return render_template("patches/view.html", patch=patch, agent_configured=is_configured())


@patches_bp.route("/<int:patch_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "analyst")
def edit_patch(patch_id):
    try:
        patch = tenant_filter(Patch.query, Patch).filter_by(id=patch_id).first()
    except Exception as exc:
        logger.exception("edit_patch: error — %s", exc)
        return render_template("errors/500.html"), 500

    if patch is None:
        flash("Patch not found.", "warning")
        return redirect(url_for("patches.list_patches"))

    if request.method == "POST":
        try:
            patch.title = request.form["title"].strip()
            patch.vendor = request.form.get("vendor", "").strip()
            patch.patch_id_vendor = request.form.get("patch_id_vendor", "").strip()
            patch.cve_ids = request.form.get("cve_ids", "").strip()
            patch.severity_vendor = request.form.get("severity_vendor", "")
            cvss = request.form.get("cvss_score", "")
            epss = request.form.get("epss_score", "")
            release = request.form.get("release_date", "")
            patch.cvss_score = float(cvss) if cvss else None
            patch.epss_score = float(epss) if epss else None
            patch.exploitability = request.form.get("exploitability", "unknown")
            patch.description = request.form.get("description", "").strip()
            patch.release_date = datetime.date.fromisoformat(release) if release else None
            patch.status = request.form.get("status", patch.status)

            asset_ids = request.form.getlist("asset_ids")
            if asset_ids:
                assets = tenant_filter(Asset.query, Asset).filter(Asset.id.in_(asset_ids)).all()
                patch.affected_assets = assets
            else:
                patch.affected_assets = []

            db.session.commit()
            log_audit("patch_updated", "Patch", patch.id, f"Updated patch: {patch.title}")
        except Exception as exc:
            logger.exception("edit_patch POST: error — %s", exc)
            db.session.rollback()
            flash("Failed to update patch.", "danger")
            return render_template("patches/form.html", patch=patch, assets=[], agent_configured=is_configured()), 500

        flash("Patch updated.", "success")
        return redirect(url_for("patches.view_patch", patch_id=patch.id))

    try:
        assets = tenant_filter(Asset.query, Asset).order_by(Asset.name).all()
    except Exception as exc:
        logger.exception("edit_patch GET assets: error — %s", exc)
        assets = []
    return render_template("patches/form.html", patch=patch, assets=assets, agent_configured=is_configured())


@patches_bp.route("/<int:patch_id>/analyze", methods=["POST"])
@login_required
@role_required("admin", "analyst")
def analyze(patch_id):
    try:
        patch = tenant_filter(Patch.query, Patch).filter_by(id=patch_id).first()
    except Exception as exc:
        logger.exception("analyze: db error — %s", exc)
        return jsonify({"error": "Database error", "detail": str(exc)}), 500

    if patch is None:
        return jsonify({"error": "Patch not found"}), 404

    patch_data = {
        "id": patch.id,
        "title": patch.title,
        "vendor": patch.vendor,
        "patch_id_vendor": patch.patch_id_vendor,
        "cve_ids": patch.cve_ids,
        "severity_vendor": patch.severity_vendor,
        "cvss_score": patch.cvss_score,
        "epss_score": patch.epss_score,
        "exploitability": patch.exploitability,
        "description": patch.description,
        "affected_assets": [
            {"name": a.name, "criticality": a.criticality, "environment": a.environment, "exposure": a.exposure}
            for a in patch.affected_assets
        ],
    }

    try:
        result = analyze_patch(patch_data, current_user.tenant.name)
    except KindoNotConfigured as exc:
        return jsonify({"error": "Agent not configured", "detail": str(exc)}), 422
    except KindoAgentError as exc:
        logger.exception("analyze: agent error — %s", exc)
        return jsonify({"error": "Analysis failed", "detail": str(exc)}), 500

    if result is None:
        return jsonify({"error": "Empty analysis result"}), 500

    try:
        patch.priority_score = result.get("score")
        patch.risk_level = result.get("risk_level")
        patch.ai_summary = result.get("summary")
        patch.ai_analysis = result
        patch.status = "analyzed"
        db.session.commit()
        log_audit("patch_analyzed", "Patch", patch.id, f"AI analysis completed. Score: {patch.priority_score}")
    except Exception as exc:
        logger.exception("analyze: save error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed to save analysis", "detail": str(exc)}), 500

    return jsonify({"ok": True, "result": result})


@patches_bp.route("/<int:patch_id>/enrich", methods=["POST"])
@login_required
@role_required("admin", "analyst")
def enrich(patch_id):
    try:
        patch = tenant_filter(Patch.query, Patch).filter_by(id=patch_id).first()
    except Exception as exc:
        logger.exception("enrich: db error — %s", exc)
        return jsonify({"error": "Database error", "detail": str(exc)}), 500

    if patch is None:
        return jsonify({"error": "Patch not found"}), 404

    patch_data = {
        "id": patch.id,
        "title": patch.title,
        "vendor": patch.vendor,
        "patch_id_vendor": patch.patch_id_vendor,
        "cve_ids": patch.cve_ids,
        "cvss_score": patch.cvss_score,
        "epss_score": patch.epss_score,
        "description": patch.description,
    }

    try:
        result = enrich_patch(patch_data, current_user.tenant.name)
    except KindoNotConfigured as exc:
        return jsonify({"error": "Agent not configured", "detail": str(exc)}), 422
    except KindoAgentError as exc:
        logger.exception("enrich: agent error — %s", exc)
        return jsonify({"error": "Enrichment failed", "detail": str(exc)}), 500

    if result is None:
        return jsonify({"error": "Empty enrichment result"}), 500

    try:
        patch.ai_analysis = result
        patch.ai_summary = result.get("summary", patch.ai_summary)
        db.session.commit()
        log_audit("patch_enriched", "Patch", patch.id, "AI enrichment completed")
    except Exception as exc:
        logger.exception("enrich: save error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed to save enrichment", "detail": str(exc)}), 500

    return jsonify({"ok": True, "result": result})


@patches_bp.route("/<int:patch_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_patch(patch_id):
    try:
        patch = tenant_filter(Patch.query, Patch).filter_by(id=patch_id).first()
    except Exception as exc:
        logger.exception("delete_patch: error — %s", exc)
        flash("Failed to delete patch.", "danger")
        return redirect(url_for("patches.list_patches"))

    if patch is None:
        flash("Patch not found.", "warning")
        return redirect(url_for("patches.list_patches"))

    try:
        title = patch.title
        db.session.delete(patch)
        db.session.commit()
        log_audit("patch_deleted", "Patch", patch_id, f"Deleted patch: {title}")
    except Exception as exc:
        logger.exception("delete_patch: error — %s", exc)
        db.session.rollback()
        flash("Failed to delete patch.", "danger")
        return redirect(url_for("patches.list_patches"))

    flash("Patch deleted.", "info")
    return redirect(url_for("patches.list_patches"))
