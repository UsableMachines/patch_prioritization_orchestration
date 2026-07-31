import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///patch_prioritization.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_NAME"] = "patch_prioritization_orchestration_session"
    app.config["SESSION_COOKIE_PATH"] = os.environ.get("SESSION_COOKIE_PATH", "/")
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["WTF_CSRF_TIME_LIMIT"] = None

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.patches import patches_bp
    from app.routes.assets import assets_bp
    from app.routes.rollout import rollout_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(patches_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(rollout_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    with app.app_context():
        db.create_all()
        _seed_defaults(app)

    return app


def _seed_defaults(app):
    """Create default tenant, admin user, and roles if empty."""
    from app.models import Tenant, User, Role

    if db.session.query(Tenant).first():
        return

    # Default roles
    roles = {
        "admin": Role(name="admin", description="Full administrative access"),
        "analyst": Role(name="analyst", description="Can analyze and prioritize patches"),
        "operator": Role(name="operator", description="Can execute rollout plans"),
        "viewer": Role(name="viewer", description="Read-only access"),
    }
    for r in roles.values():
        db.session.add(r)

    tenant = Tenant(name="Default Organization", slug="default")
    db.session.add(tenant)
    db.session.flush()

    admin = User(
        username="admin",
        email="admin@example.com",
        tenant_id=tenant.id,
        is_active=True,
    )
    admin.set_password("admin")
    admin.roles.append(roles["admin"])
    db.session.add(admin)
    db.session.commit()
    app.logger.info("Seeded default tenant, roles, and admin user (admin/admin).")
