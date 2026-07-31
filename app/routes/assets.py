import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Asset
from app.services.rbac import role_required, tenant_filter, log_audit

logger = logging.getLogger(__name__)
assets_bp = Blueprint("assets", __name__, url_prefix="/assets")


@assets_bp.route("/")
@login_required
def list_assets():
    try:
        q = tenant_filter(Asset.query, Asset)
        crit_filter = request.args.get("criticality")
        env_filter = request.args.get("environment")
        if crit_filter:
            q = q.filter(Asset.criticality == crit_filter)
        if env_filter:
            q = q.filter(Asset.environment == env_filter)
        assets = q.order_by(Asset.name).all()
    except Exception as exc:
        logger.exception("list_assets: error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("assets/list.html", assets=assets)


@assets_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "analyst", "operator")
def create_asset():
    if request.method == "POST":
        try:
            asset = Asset(
                name=request.form["name"].strip(),
                hostname=request.form.get("hostname", "").strip(),
                ip_address=request.form.get("ip_address", "").strip(),
                os_type=request.form.get("os_type", "").strip(),
                os_version=request.form.get("os_version", "").strip(),
                criticality=request.form.get("criticality", "medium"),
                environment=request.form.get("environment", "production"),
                exposure=request.form.get("exposure", "internal"),
                business_unit=request.form.get("business_unit", "").strip(),
                owner=request.form.get("owner", "").strip(),
                tenant_id=current_user.tenant_id,
            )
            db.session.add(asset)
            db.session.commit()
            log_audit("asset_created", "Asset", asset.id, f"Created asset: {asset.name}")
        except Exception as exc:
            logger.exception("create_asset: error — %s", exc)
            db.session.rollback()
            flash("Failed to create asset.", "danger")
            return render_template("assets/form.html", asset=None), 500

        flash("Asset created.", "success")
        return redirect(url_for("assets.view_asset", asset_id=asset.id))
    return render_template("assets/form.html", asset=None)


@assets_bp.route("/<int:asset_id>")
@login_required
def view_asset(asset_id):
    try:
        asset = tenant_filter(Asset.query, Asset).filter_by(id=asset_id).first()
    except Exception as exc:
        logger.exception("view_asset: error — %s", exc)
        return render_template("errors/500.html"), 500

    if asset is None:
        flash("Asset not found.", "warning")
        return redirect(url_for("assets.list_assets"))

    return render_template("assets/view.html", asset=asset)


@assets_bp.route("/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "analyst", "operator")
def edit_asset(asset_id):
    try:
        asset = tenant_filter(Asset.query, Asset).filter_by(id=asset_id).first()
    except Exception as exc:
        logger.exception("edit_asset: error — %s", exc)
        return render_template("errors/500.html"), 500

    if asset is None:
        flash("Asset not found.", "warning")
        return redirect(url_for("assets.list_assets"))

    if request.method == "POST":
        try:
            asset.name = request.form["name"].strip()
            asset.hostname = request.form.get("hostname", "").strip()
            asset.ip_address = request.form.get("ip_address", "").strip()
            asset.os_type = request.form.get("os_type", "").strip()
            asset.os_version = request.form.get("os_version", "").strip()
            asset.criticality = request.form.get("criticality", "medium")
            asset.environment = request.form.get("environment", "production")
            asset.exposure = request.form.get("exposure", "internal")
            asset.business_unit = request.form.get("business_unit", "").strip()
            asset.owner = request.form.get("owner", "").strip()
            db.session.commit()
            log_audit("asset_updated", "Asset", asset.id, f"Updated asset: {asset.name}")
        except Exception as exc:
            logger.exception("edit_asset POST: error — %s", exc)
            db.session.rollback()
            flash("Failed to update asset.", "danger")
            return render_template("assets/form.html", asset=asset), 500

        flash("Asset updated.", "success")
        return redirect(url_for("assets.view_asset", asset_id=asset.id))
    return render_template("assets/form.html", asset=asset)


@assets_bp.route("/<int:asset_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_asset(asset_id):
    try:
        asset = tenant_filter(Asset.query, Asset).filter_by(id=asset_id).first()
    except Exception as exc:
        logger.exception("delete_asset: error — %s", exc)
        flash("Failed to delete asset.", "danger")
        return redirect(url_for("assets.list_assets"))

    if asset is None:
        flash("Asset not found.", "warning")
        return redirect(url_for("assets.list_assets"))

    try:
        name = asset.name
        db.session.delete(asset)
        db.session.commit()
        log_audit("asset_deleted", "Asset", asset_id, f"Deleted asset: {name}")
    except Exception as exc:
        logger.exception("delete_asset: error — %s", exc)
        db.session.rollback()
        flash("Failed to delete asset.", "danger")
        return redirect(url_for("assets.list_assets"))

    flash("Asset deleted.", "info")
    return redirect(url_for("assets.list_assets"))
