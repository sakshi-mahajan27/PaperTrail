"""
Audit logging utility. Call log_action() from signals or views.
"""
import threading
from .models import AuditLog

_current_user = threading.local()


def set_current_user(user):
    _current_user.value = user


def get_current_user():
    return getattr(_current_user, "value", None)


def model_to_dict_simple(instance):
    """Convert a model instance to a plain dict of field values (non-relational)."""
    data = {}
    for field in instance._meta.concrete_fields:
        val = getattr(instance, field.attname, None)
        if val is not None:
            data[field.name] = str(val)
        else:
            data[field.name] = None
    return data


def log_action(user, action, instance, prev_value=None):
    new_value = model_to_dict_simple(instance) if action != AuditLog.ACTION_DELETED else None
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=instance.pk,
        object_repr=str(instance)[:300],
        prev_value=prev_value,
        new_value=new_value,
    )
