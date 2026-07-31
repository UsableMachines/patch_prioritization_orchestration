import logging
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import RolloutPlan, RolloutStep, Patch, Asset
from app.services.rbac import role_required, tenant_filter, log_audit
from app.services.kindo_agent import (
    generate_rollout_plan, is_configured,
    KindoAgentError, KindoNotConfigured,
)

logger = logging.getLogger(__name__)
rollout_bp = Blueprint("rollout", __name__, url_prefix="/rollout")


@rollout_bp.route("/")
@login_required
def list_plans():
    try:
        plans = (
            tenant_filter(RolloutPlan.query, RolloutPlan)
            .order_by(RolloutPlan.created_at.desc())
            .all()
        )
    except Exception as exc:
        logger.exception("list_plans: error — %s", exc)
        return render_template("errors/500.html"), 500

    return render_template("rollout/list.html", plans=plans, agent_configured=is_configured())


@rollout_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "analyst", "operator")
def create_plan():
    if request.method == "POST":
        try:
            plan = RolloutPlan(
                name=request.form["name"].strip(),
                description=request.form.get("description", "").strip(),
                status="draft",
                created_by_id=current_user.id,
                tenant_id=current_user.tenant_id,
            )
            schedule_start = request.form.get("schedule_start", "")
            schedule_end = request.form.get("schedule_end", "")
            if schedule_start:
                plan.schedule_start = datetime.datetime.fromisoformat(schedule_start)
            if schedule_end:
                plan.schedule_end = datetime.datetime.fromisoformat(schedule_end)

            db.session.add(plan)
            db.session.flush()

            # Add manual steps from selected patches
            patch_ids = request.form.getlist("patch_ids")
            order = 0
            for pid in patch_ids:
                patch = tenant_filter(Patch.query, Patch).filter_by(id=int(pid)).first()
                if patch:
                    for asset in patch.affected_assets:
                        step = RolloutStep(
                            plan_id=plan.id,
                            order=order,
                            patch_id=patch.id,
                            asset_id=asset.id,
                            action=f"Deploy {patch.title} to {asset.name}",
                            status="pending",
                        )
                        db.session.add(step)
                        order += 1

            db.session.commit()
            log_audit("plan_created", "RolloutPlan", plan.id, f"Created plan: {plan.name}")
        except Exception as exc:
            logger.exception("create_plan: error — %s", exc)
            db.session.rollback()
            flash("Failed to create rollout plan.", "danger")
            return redirect(url_for("rollout.create_plan"))

        flash("Rollout plan created.", "success")
        return redirect(url_for("rollout.view_plan", plan_id=plan.id))

    try:
        patches = (
            tenant_filter(Patch.query, Patch)
            .filter(Patch.status.in_(["analyzed", "pending"]))
            .order_by(Patch.priority_score.desc().nullslast())
            .all()
        )
    except Exception as exc:
        logger.exception("create_plan GET: error — %s", exc)
        patches = []

    return render_template("rollout/form.html", plan=None, patches=patches, agent_configured=is_configured())


@rollout_bp.route("/<int:plan_id>")
@login_required
def view_plan(plan_id):
    try:
        plan = tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(id=plan_id).first()
    except Exception as exc:
        logger.exception("view_plan: error — %s", exc)
        return render_template("errors/500.html"), 500

    if plan is None:
        flash("Rollout plan not found.", "warning")
        return redirect(url_for("rollout.list_plans"))

    return render_template("rollout/view.html", plan=plan, agent_configured=is_configured())


@rollout_bp.route("/<int:plan_id>/generate", methods=["POST"])
@login_required
@role_required("admin", "analyst")
def generate_plan(plan_id):
    try:
        plan = tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(id=plan_id).first()
    except Exception as exc:
        logger.exception("generate_plan: db error — %s", exc)
        return jsonify({"error": "Database error", "detail": str(exc)}), 500

    if plan is None:
        return jsonify({"error": "Plan not found"}), 404

    try:
        patches = tenant_filter(Patch.query, Patch).filter(
            Patch.status.in_(["analyzed", "pending"])
        ).all()
        assets = tenant_filter(Asset.query, Asset).all()
    except Exception as exc:
        logger.exception("generate_plan: query error — %s", exc)
        return jsonify({"error": "Failed to load data", "detail": str(exc)}), 500

    patch_data = [
        {
            "id": p.id, "title": p.title, "vendor": p.vendor,
            "cve_ids": p.cve_ids, "priority_score": p.priority_score,
            "risk_level": p.risk_level, "exploitability": p.exploitability,
        }
        for p in patches
    ]
    asset_data = [
        {
            "id": a.id, "name": a.name, "criticality": a.criticality,
            "environment": a.environment, "exposure": a.exposure,
        }
        for a in assets
    ]

    try:
        result = generate_rollout_plan(patch_data, asset_data, current_user.tenant.name)
    except KindoNotConfigured as exc:
        return jsonify({"error": "Agent not configured", "detail": str(exc)}), 422
    except KindoAgentError as exc:
        logger.exception("generate_plan: agent error — %s", exc)
        return jsonify({"error": "Plan generation failed", "detail": str(exc)}), 500

    if result is None:
        return jsonify({"error": "Empty plan result"}), 500

    try:
        plan.ai_plan = result
        db.session.commit()
        log_audit("plan_generated", "RolloutPlan", plan.id, "AI rollout plan generated")
    except Exception as exc:
        logger.exception("generate_plan: save error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed to save plan", "detail": str(exc)}), 500

    return jsonify({"ok": True, "result": result})


@rollout_bp.route("/<int:plan_id>/approve", methods=["POST"])
@login_required
@role_required("admin")
def approve_plan(plan_id):
    try:
        plan = tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(id=plan_id).first()
    except Exception as exc:
        logger.exception("approve_plan: error — %s", exc)
        flash("Failed to approve plan.", "danger")
        return redirect(url_for("rollout.list_plans"))

    if plan is None:
        flash("Plan not found.", "warning")
        return redirect(url_for("rollout.list_plans"))

    try:
        plan.status = "approved"
        plan.approved_by_id = current_user.id
        db.session.commit()
        log_audit("plan_approved", "RolloutPlan", plan.id, f"Approved plan: {plan.name}")
    except Exception as exc:
        logger.exception("approve_plan: save error — %s", exc)
        db.session.rollback()
        flash("Failed to approve plan.", "danger")
        return redirect(url_for("rollout.view_plan", plan_id=plan.id))

    flash("Plan approved.", "success")
    return redirect(url_for("rollout.view_plan", plan_id=plan.id))


@rollout_bp.route("/<int:plan_id>/step/<int:step_id>/status", methods=["POST"])
@login_required
@role_required("admin", "operator")
def update_step_status(plan_id, step_id):
    try:
        plan = tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(id=plan_id).first()
    except Exception as exc:
        logger.exception("update_step: error — %s", exc)
        return jsonify({"error": "Database error", "detail": str(exc)}), 500

    if plan is None:
        return jsonify({"error": "Plan not found"}), 404

    try:
        step = RolloutStep.query.filter_by(id=step_id, plan_id=plan_id).first()
    except Exception as exc:
        logger.exception("update_step: error — %s", exc)
        return jsonify({"error": "Database error", "detail": str(exc)}), 500

    if step is None:
        return jsonify({"error": "Step not found"}), 404

    new_status = request.json.get("status", "") if request.is_json else request.form.get("status", "")
    if new_status not in ("pending", "in_progress", "completed", "failed", "skipped"):
        return jsonify({"error": "Invalid status"}), 400

    try:
        step.status = new_status
        if new_status == "completed":
            step.completed_at = datetime.datetime.utcnow()
        db.session.commit()
        log_audit("step_updated", "RolloutStep", step.id, f"Status → {new_status}")
    except Exception as exc:
        logger.exception("update_step: save error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed to save", "detail": str(exc)}), 500

    return jsonify({"ok": True, "status": new_status})


@rollout_bp.route("/<int:plan_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_plan(plan_id):
    try:
        plan = tenant_filter(RolloutPlan.query, RolloutPlan).filter_by(id=plan_id).first()
    except Exception as exc:
        logger.exception("delete_plan: error — %s", exc)
        flash("Failed to delete plan.", "danger")
        return redirect(url_for("rollout.list_plans"))

    if plan is None:
        flash("Plan not found.", "warning")
        return redirect(url_for("rollout.list_plans"))

    try:
        name = plan.name
        RolloutStep.query.filter_by(plan_id=plan.id).delete()
        db.session.delete(plan)
        db.session.commit()
        log_audit("plan_deleted", "RolloutPlan", plan_id, f"Deleted plan: {name}")
    except Exception as exc:
        logger.exception("delete_plan: error — %s", exc)
        db.session.rollback()
        flash("Failed to delete plan.", "danger")
        return redirect(url_for("rollout.list_plans"))

    flash("Plan deleted.", "info")
    return redirect(url_for("rollout.list_plans"))
