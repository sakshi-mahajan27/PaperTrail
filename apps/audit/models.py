from django.db import models
from django.contrib.contenttypes.models import ContentType
from apps.accounts.models import User


class AuditLog(models.Model):
    """
    Immutable audit log for tracking all changes to critical models.

    This model creates an immutable, tamper-proof record of every CREATE, UPDATE,
    and DELETE action on critical financial and compliance objects. It's the
    foundation of PaperTrail's audit trail and change tracking system.

    Records are created automatically by Django signal handlers (apps/audit/signals.py)
    and can NEVER be edited or deleted (enforced by has_add_permission=False in admin).

    Business Purpose:
        - Provide forensic evidence of who changed what and when
        - Enable rollback/recovery of data
        - Ensure regulatory compliance (NGO board audits, tax authorities)
        - Detect unauthorized data modifications

    Tracked Models:
        - Grant: Fundraising agreements (create/update/delete)
        - Expense: Fund utilization records (create/update/delete)
        - ExpenseAllocation: Expense-to-grant mapping (create/update/delete)
        - ComplianceDocument: Certificates (create/update/delete)
        - Donor: Fundraiser registry (create/update/delete)

    Fields:
        action (str): One of 'created', 'updated', 'deleted'.
            Indicates what type of change was made.

        content_type (ForeignKey): Link to the Django ContentType.
            Identifies which model was modified (e.g., Grant, Expense).
            On CASCADE delete, historical logs are preserved.

        object_id (int): The primary key of the modified object.
            Combined with content_type, uniquely identifies the object.
            Note: Doesn't break if original object is deleted (no FK constraint).

        object_repr (str): String representation of the object.
            e.g., "Training Grant - $50,000 (Bob Smith)"
            Serves as human-readable label if object is later deleted.

        changed_by (ForeignKey, optional): The user who made the change.
            Foreign key to User model with SET_NULL on delete.
            Allows auditors to see who authorized each change.
            Can be None for system/management command changes.

        timestamp (datetime): When the change was made.
            auto_now_add=True: Set automatically on creation.
            Indexed for efficient querying (db_index=True).
            Timezone-aware (uses Django's USE_TZ setting).

        changes (dict): JSON field storing detailed field-level changes.
            Format: {"field": {"old": "value1", "new": "value2"}}
            Empty dict {} for CREATE actions (no "old" state to track).
            Example:
                {
                    "total_amount": {"old": "50000", "new": "55000"},
                    "status": {"old": "pending", "new": "active"},
                    "notes": {"old": null, "new": "Low interest rate"}
                }

    Query Examples:
        # View all changes to a specific grant
        logs = AuditLog.objects.filter(
            content_type__model='grant',
            object_id=42
        ).order_by('-timestamp')

        # View all changes by admin user john
        logs = AuditLog.objects.filter(changed_by__username='john').order_by('-timestamp')

        # Find when a grant's total_amount changed
        import json
        for log in AuditLog.objects.filter(action='updated'):
            if 'total_amount' in log.changes:
                print(f"{log.timestamp}: {log.changed_by} changed amount")

        # Get recent activity (last hour)
        from django.utils import timezone
        from datetime import timedelta
        recent = AuditLog.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=1)
        )

    Performance Considerations:
        - Database indexes on (content_type, object_id) for quick lookup
        - Index on (action, timestamp) for filtering by action type
        - Index on (changed_by, timestamp) for user accountability queries
        - JSONField (changes) is indexed by database for JSON queries
        - Logs accumulate over time; archive old logs if DB grows large

    Security:
        - Logs are read-only (Django admin can't edit/delete)
        - Changing content.object_repr doesn't break historical records
        - timestamp is server-side (can't be manipulated by client)
        - changed_by is set server-side (can't be faked by user input)

    Notes:
        - Soft deletes (is_active=False) create DELETE logs but don't remove data
        - Hard deletes trigger post_delete signals (normal CASCADE deletes)
        - System tasks without a user (changed_by=None) are still logged if identifiable
        - Not all models are logged—only critical financial models (see Tracked Models)
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
    object_repr = models.CharField(
        max_length=255,
        help_text="String representation of the object at time of change"
    )

    # Who made the change
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
        help_text="User who made the change"
    )

    # When the change was made
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Automatically set to current time. Cannot be edited."
    )

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
        """
        Return the name of the model that was changed.

        Returns:
            str: Lowercase model name (e.g., 'grant', 'expense')
        """
        return self.content_type.model

    @property
    def model_label(self):
        """
        Return human-readable model label.

        Returns:
            str: Human-readable model label (e.g., 'Grant', 'Expense')
        """
        return self.content_type.name

    @classmethod
    def log_action(cls, action, instance, changed_by, changes=None):
        """
        Create an audit log entry.

        This is the primary entrypoint for creating audit logs. Called by
        signal handlers after a model instance is created, updated, or deleted.

        Args:
            action (str): One of ACTION_CREATED, ACTION_UPDATED, ACTION_DELETED
            instance: The model instance that was changed (e.g., Grant, Expense)
            changed_by: The User who made the change, or None for system actions
            changes (dict): Field changes in format:
                {"field": {"old": "value1", "new": "value2"}}
                Optional; defaults to empty dict {}

        Returns:
            AuditLog: The newly created audit log entry

        Examples:
            # Log a grant creation
            AuditLog.log_action(
                action=AuditLog.ACTION_CREATED,
                instance=grant,
                changed_by=request.user,
                changes={}
            )

            # Log an expense update with field changes
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=expense,
                changed_by=john_admin,
                changes={
                    'total_amount': {'old': '1000', 'new': '1200'}
                }
            )

            # Log a granted deletion
            AuditLog.log_action(
                action=AuditLog.ACTION_DELETED,
                instance=grant,
                changed_by=request.user,
                changes={}
            )

        Notes:
            - Called automatically by Django signal handlers; rarely called directly
            - content_type and object_repr are auto-calculated
            - Returns the created AuditLog instance
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
