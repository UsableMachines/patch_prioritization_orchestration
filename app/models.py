import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# ── Association tables ────────────────────────────────────────────────

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

patch_assets = db.Table(
    "patch_assets",
    db.Column("patch_id", db.Integer, db.ForeignKey("patches.id"), primary_key=True),
    db.Column("asset_id", db.Integer, db.ForeignKey("assets.id"), primary_key=True),
)


# ── Models ────────────────────────────────────────────────────────────

class Tenant(db.Model):
    __tablename__ = "tenants"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    users = db.relationship("User", backref="tenant", lazy=True)
    assets = db.relationship("Asset", backref="tenant", lazy=True)
    patches = db.relationship("Patch", backref="tenant", lazy=True)
    rollout_plans = db.relationship("RolloutPlan", backref="tenant", lazy=True)


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    roles = db.relationship("Role", secondary=user_roles, backref="users", lazy="joined")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, role_name):
        return any(r.name == role_name for r in self.roles)

    def has_any_role(self, *role_names):
        return any(r.name in role_names for r in self.roles)


class Asset(db.Model):
    __tablename__ = "assets"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    hostname = db.Column(db.String(200))
    ip_address = db.Column(db.String(45))
    os_type = db.Column(db.String(100))
    os_version = db.Column(db.String(100))
    criticality = db.Column(db.String(20), default="medium")  # critical/high/medium/low
    environment = db.Column(db.String(50), default="production")  # production/staging/dev/test
    exposure = db.Column(db.String(20), default="internal")  # external/dmz/internal
    business_unit = db.Column(db.String(200))
    owner = db.Column(db.String(200))
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Patch(db.Model):
    __tablename__ = "patches"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    vendor = db.Column(db.String(100))
    patch_id_vendor = db.Column(db.String(100))  # e.g. KB5028185, CVE-2026-1234
    cve_ids = db.Column(db.Text)  # comma-separated CVEs
    severity_vendor = db.Column(db.String(20))  # vendor-reported severity
    cvss_score = db.Column(db.Float)
    epss_score = db.Column(db.Float)
    exploitability = db.Column(db.String(20), default="unknown")  # active/poc/theoretical/unknown
    description = db.Column(db.Text)
    release_date = db.Column(db.Date)
    # Computed fields
    priority_score = db.Column(db.Float)
    risk_level = db.Column(db.String(20))  # critical/high/medium/low/informational
    ai_summary = db.Column(db.Text)
    ai_analysis = db.Column(db.JSON)
    status = db.Column(db.String(30), default="pending")  # pending/analyzed/scheduled/deployed/verified/deferred
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    affected_assets = db.relationship("Asset", secondary=patch_assets, backref="patches", lazy="joined")


class RolloutPlan(db.Model):
    __tablename__ = "rollout_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default="draft")  # draft/approved/in_progress/completed/cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    ai_plan = db.Column(db.JSON)
    schedule_start = db.Column(db.DateTime)
    schedule_end = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    steps = db.relationship("RolloutStep", backref="plan", lazy=True, order_by="RolloutStep.order")


class RolloutStep(db.Model):
    __tablename__ = "rollout_steps"
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("rollout_plans.id"), nullable=False)
    order = db.Column(db.Integer, default=0)
    patch_id = db.Column(db.Integer, db.ForeignKey("patches.id"))
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"))
    action = db.Column(db.String(200))
    status = db.Column(db.String(30), default="pending")  # pending/in_progress/completed/failed/skipped
    notes = db.Column(db.Text)
    scheduled_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    patch = db.relationship("Patch")
    asset = db.relationship("Asset")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user = db.relationship("User")
