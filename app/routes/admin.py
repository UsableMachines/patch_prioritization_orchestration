import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Role, Tenant, AuditLog
from app.services.rbac import role_required, tenant_filter

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
@login_required
def check_admin():
    if not current_user.has_role("admin"):
        flash("Admin access required.", "danger")
        return redirect(url_for("main.dashboard"))


@admin_bp.route("/")
def admin_index():
    return redirect(url_for("admin.users"))


@admin_bp.route("/users")
def users():
    try:
        user_list = tenant_filter(User.query, User).order_by(User.username).all()
    except Exception as exc:
        logger.exception("admin users: error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("admin/users.html", users=user_list)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    try:
        user = tenant_filter(User.query, User).filter_by(id=user_id).first()
    except Exception as exc:
        logger.exception("admin edit_user: error — %s", exc)
        return render_template("errors/500.html"), 500

    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("admin.users"))

    if request.method == "POST":
        try:
            user.email = request.form.get("email", user.email).strip()
            user.is_active = request.form.get("is_active") == "on"

            new_password = request.form.get("new_password", "").strip()
            if new_password:
                user.set_password(new_password)

            role_names = request.form.getlist("roles")
            user.roles = Role.query.filter(Role.name.in_(role_names)).all()

            db.session.commit()
        except Exception as exc:
            logger.exception("admin edit_user: error — %s", exc)
            db.session.rollback()
            flash("Failed to update user.", "danger")
            return render_template("admin/edit_user.html", user=user, all_roles=Role.query.all()), 500

        flash("User updated.", "success")
        return redirect(url_for("admin.users"))

    try:
        all_roles = Role.query.all()
    except Exception as exc:
        logger.exception("admin edit_user roles: error — %s", exc)
        all_roles = []
    return render_template("admin/edit_user.html", user=user, all_roles=all_roles)


@admin_bp.route("/audit")
def audit():
    try:
        logs = (
            tenant_filter(AuditLog.query, AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(200)
            .all()
        )
    except Exception as exc:
        logger.exception("admin audit: error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("admin/audit.html", logs=logs)


@admin_bp.route("/tenants")
def tenants():
    try:
        tenant_list = Tenant.query.order_by(Tenant.name).all()
    except Exception as exc:
        logger.exception("admin tenants: error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("admin/tenants.html", tenants=tenant_list)
