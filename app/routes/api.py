import logging
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models import Patch, Asset, RolloutPlan, AuditLog
from app.services.rbac import role_required, tenant_filter

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)


@api_bp.route("/stats")
@login_required
def stats():
    try:
        data = {
            "patches": {
                "total": tenant_filter(Patch.query, Patch).count(),
                "critical": tenant_filter(Patch.query, Patch).filter_by(risk_level="critical").count(),
                "high": tenant_filter(Patch.query, Patch).filter_by(risk_level="high").count(),
                "medium": tenant_filter(Patch.query, Patch).filter_by(risk_level="medium").count(),
                "low": tenant_filter(Patch.query, Patch).filter_by(risk_level="low").count(),
                "pending": tenant_filter(Patch.query, Patch).filter_by(status="pending").count(),
                "analyzed": tenant_filter(Patch.query, Patch).filter_by(status="analyzed").count(),
                "deployed": tenant_filter(Patch.query, Patch).filter_by(status="deployed").count(),
            },
            "assets": {
                "total": tenant_filter(Asset.query, Asset).count(),
            },
            "plans": {
                "total": tenant_filter(RolloutPlan.query, RolloutPlan).count(),
                "draft": tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(status="draft").count(),
                "approved": tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(status="approved").count(),
                "in_progress": tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(status="in_progress").count(),
            },
        }
    except Exception as exc:
        logger.exception("stats: error — %s", exc)
        return jsonify({"error": "Failed to load stats", "detail": str(exc)}), 500

    return jsonify(data)


@api_bp.route("/audit-log")
@login_required
@role_required("admin")
def audit_log():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 50, type=int), 100)
        logs = (
            tenant_filter(AuditLog.query, AuditLog)
            .order_by(AuditLog.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
    except Exception as exc:
        logger.exception("audit_log: error — %s", exc)
        return jsonify({"error": "Failed to load audit log", "detail": str(exc)}), 500

    return jsonify({
        "items": [
            {
                "id": l.id,
                "user": l.user.username if l.user else None,
                "action": l.action,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs.items
        ],
        "total": logs.total,
        "page": logs.page,
        "pages": logs.pages,
    })
