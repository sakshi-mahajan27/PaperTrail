"""
Utility helpers for audit tracking.

Usage: Before saving a model instance, call track_changes() to capture
old values, then the post_save signal will automatically compare and log changes.

Example:
    from apps.audit.utils import track_changes
    
    grant = Grant.objects.get(id=1)
    grant.name = "New Name"
    track_changes(grant)  # Capture old values
    grant.save()  # Signal will handle logging
"""

from django.core.serializers import deserialize
from django.core.serializers.json import DjangoJSONEncoder
import json


def track_changes(instance):
    """
    Capture the current field values before a save operation.
    This allows the post_save signal to detect what changed.

    Call this method before modifying and saving a model instance:

    Example:
        obj = MyModel.objects.get(pk=1)
        track_changes(obj)  # Capture current state
        obj.field_name = "new value"
        obj.save()  # Signal will detect the change
    """
    # Store original values
    instance._original_values = {}
    for field in instance._meta.get_fields():
        if field.name not in {'id', 'created_at', 'updated_at', 'yellow_alert_sent'}:
            try:
                value = getattr(instance, field.name, None)
                # Store serializable version
                if hasattr(value, 'isoformat'):  # datetime/date
                    instance._original_values[field.name] = value.isoformat()
                else:
                    instance._original_values[field.name] = value
            except (AttributeError, Exception):
                pass


def serialize_field_value(value):
    """
    Safely serialize a field value to a JSON-compatible format.
    """
    if value is None:
        return None
    if hasattr(value, 'isoformat'):  # datetime/date objects
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def get_model_change_summary(instance, old_instance):
    """
    Compare two model instances and return a summary of changes.

    Returns:
        dict: {field_name: {'old': old_value, 'new': new_value}}
    """
    changes = {}
    exclude_fields = {'id', 'created_at', 'updated_at', 'yellow_alert_sent'}

    for field in instance._meta.get_fields():
        if field.name in exclude_fields or field.many_to_one or field.many_to_many:
            continue

        try:
            old_value = getattr(old_instance, field.name, None) if old_instance else None
            new_value = getattr(instance, field.name, None)

            # Convert to serializable format
            old_value = serialize_field_value(old_value)
            new_value = serialize_field_value(new_value)

            # Only record if value actually changed
            if old_value != new_value:
                changes[field.name] = {
                    'old': old_value,
                    'new': new_value,
                }
        except (AttributeError, Exception):
            pass

    return changes
