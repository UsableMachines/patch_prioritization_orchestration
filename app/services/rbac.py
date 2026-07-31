"""RBAC decorators and helpers."""
import functools
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def role_required(*role_names):
    """Decorator: require user to have at least one of the listed roles."""
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not current_user.has_any_role(*role_names):
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def tenant_filter(query, model):
    """Filter a query to the current user's tenant."""
    return query.filter(model.tenant_id == current_user.tenant_id)


def log_audit(action, entity_type=None, entity_id=None, detail=None):
    """Write an audit log entry."""
    from app import db
    from app.models import AuditLog
    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        tenant_id=current_user.tenant_id if current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    db.session.add(entry)
    db.session.commit()
