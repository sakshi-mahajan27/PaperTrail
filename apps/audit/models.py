from django.db import models
from django.contrib.contenttypes.models import ContentType
from apps.accounts.models import User


class AuditLog(models.Model):
    """
    Immutable audit log for tracking all changes to critical models.
    Records every Create, Update, and Delete action.
    """

    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_DELETED = "deleted"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_UPDATED, "Updated"),
        (ACTION_DELETED, "Deleted"),
    ]

    # What action was performed
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    # Which model and object were affected
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    object_repr = models.CharField(max_length=255, help_text="String representation of the object")

    # Who made the change
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
        help_text="User who made the change"
    )

    # When the change was made
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # What changed (old values vs new values)
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON field storing {'field_name': {'old': old_value, 'new': new_value}}"
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        # Prevent deletion of audit logs
        permissions = [
            ("view_audit_logs", "Can view audit logs"),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["changed_by", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.object_repr} by {self.changed_by} at {self.timestamp}"

    @property
    def model_name(self):
        """Return the name of the model that was changed"""
        return self.content_type.model

    @property
    def model_label(self):
        """Return human-readable model label"""
        return self.content_type.name

    @classmethod
    def log_action(cls, action, instance, changed_by, changes=None):
        """
        Create an audit log entry.

        Args:
            action: One of ACTION_CREATED, ACTION_UPDATED, ACTION_DELETED
            instance: The model instance that was changed
            changed_by: The User who made the change
            changes: Dict of field changes {'field': {'old': value, 'new': value}}
        """
        if changes is None:
            changes = {}

        content_type = ContentType.objects.get_for_model(instance)
        object_repr = str(instance)

        return cls.objects.create(
            action=action,
            content_type=content_type,
            object_id=instance.id,
            object_repr=object_repr,
            changed_by=changed_by,
            changes=changes
        )
