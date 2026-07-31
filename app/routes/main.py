import logging
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Patch, Asset, RolloutPlan, AuditLog
from app.services.rbac import tenant_filter
from app.services.kindo_agent import is_configured

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return render_template("main/dashboard.html")
    return render_template("main/landing.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    try:
        patch_count = tenant_filter(Patch.query, Patch).count()
        asset_count = tenant_filter(Asset.query, Asset).count()
        plan_count = tenant_filter(RolloutPlan.query, RolloutPlan).count()
        critical_patches = tenant_filter(Patch.query, Patch).filter(
            Patch.risk_level == "critical"
        ).count()
        recent_patches = (
            tenant_filter(Patch.query, Patch)
            .order_by(Patch.created_at.desc())
            .limit(5)
            .all()
        )
        recent_activity = (
            tenant_filter(AuditLog.query, AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
            .all()
        )
    except Exception as exc:
        logger.exception("dashboard: service error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template(
        "main/dashboard.html",
        patch_count=patch_count,
        asset_count=asset_count,
        plan_count=plan_count,
        critical_patches=critical_patches,
        recent_patches=recent_patches,
        recent_activity=recent_activity,
        agent_configured=is_configured(),
    )


@main_bp.route("/getting-started")
@login_required
def getting_started():
    return render_template("main/getting_started.html", agent_configured=is_configured())


@main_bp.route("/settings")
@login_required
def settings():
    return render_template("main/settings.html", agent_configured=is_configured())


@main_bp.route("/toggle-theme", methods=["POST"])
@login_required
def toggle_theme():
    return jsonify({"ok": True})
