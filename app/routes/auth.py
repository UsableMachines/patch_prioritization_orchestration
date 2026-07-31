import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Tenant, Role

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = User.query.filter_by(username=username).first()
        except Exception as exc:
            logger.exception("login: db error — %s", exc)
            flash("An error occurred. Please try again.", "danger")
            return render_template("auth/login.html"), 500

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")
        if not user.is_active:
            flash("Account is disabled. Contact your administrator.", "warning")
            return render_template("auth/login.html")
        login_user(user)
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        tenant_slug = request.form.get("tenant", "default")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        try:
            if User.query.filter_by(username=username).first():
                flash("Username already taken.", "danger")
                return render_template("auth/register.html")
            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "danger")
                return render_template("auth/register.html")

            tenant = Tenant.query.filter_by(slug=tenant_slug).first()
            if not tenant:
                tenant = Tenant(name=tenant_slug.replace("-", " ").title(), slug=tenant_slug)
                db.session.add(tenant)
                db.session.flush()

            viewer_role = Role.query.filter_by(name="viewer").first()
            user = User(username=username, email=email, tenant_id=tenant.id, is_active=True)
            user.set_password(password)
            if viewer_role:
                user.roles.append(viewer_role)
            db.session.add(user)
            db.session.commit()
        except Exception as exc:
            logger.exception("register: db error — %s", exc)
            db.session.rollback()
            flash("Registration failed. Please try again.", "danger")
            return render_template("auth/register.html"), 500

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))
