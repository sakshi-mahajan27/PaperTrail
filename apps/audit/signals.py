"""
Audit logging system using Django signals.

This module implements comprehensive audit trail functionality by hooking into
Django's model signals (pre_save, post_save, post_delete) for critical models:
- Grant (fundraising agreements)
- Expense (fund utilization)
- ExpenseAllocation (allocating expenses to grants)
- ComplianceDocument (certificates)
- Donor (fundraiser registry)

ARCHITECTURE:

1. Thread-Local Storage Pattern:
   -----
   The system uses thread-local storage (_thread_locals) to track:
   - Current authenticated user (set by AuditMiddlewareUser)
   - Old instance states (captured before save for change detection)

   Why thread-local? Because Django signal handlers run in the same thread as
   the view, allowing us to access the request.user without passing it explicitly.

2. Signal Flow (on model.save()):
   -----
   a) pre_save signal fires → capture_*_old_state() stores old instance in thread-local
   b) Model is saved to database
   c) post_save signal fires → log_*_change() compares old vs new
   d) Changes are written to AuditLog table
   e) Cleanup: clear_old_instance() removes temporary data from thread-local

3. Change Detection:
   -----
   get_field_changes() compares old and new instances field-by-field and
   returns a dict: {"field": {"old": "val1", "new": "val2"}}
   This dict is stored as JSON in AuditLog.changes field.

4. User Tracking:
   -----
   get_current_user() retrieves the authenticated user from thread-local.
   If user is None or AnonymousUser, audit logging is skipped (system/management tasks).

SETUP REQUIRED:

Add to settings.py MIDDLEWARE:
    'apps.audit.signals.AuditMiddlewareUser',

This ensures set_current_user() is called for every request.

EXAMPLE LOG ENTRY:

    action='updated'
    object_repr='Training Grant - $50,000'
    changed_by=User(john_admin)
    timestamp=2025-03-23 14:30:00
    changes={
        "total_amount": {"old": "50000", "new": "55000"},
        "status": {"old": "pending", "new": "active"}
    }

QUERIES:

    # View all changes made by user
    AuditLog.objects.filter(changed_by__username='john_admin')

    # View changes to a specific grant
    AuditLog.objects.filter(
        content_type__model='grant',
        object_id=42
    ).order_by('-timestamp')

    # View only updates (exclude creates/deletes)
    AuditLog.objects.filter(action='updated')
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
import threading
import copy

from apps.grants.models import Grant
from apps.expenses.models import Expense, ExpenseAllocation
from apps.compliance.models import ComplianceDocument
from apps.donors.models import Donor
from .models import AuditLog

# Thread-local storage for tracking current user and old instances
_thread_locals = threading.local()


def get_current_user():
    """
    Retrieve the currently authenticated user from thread-local storage.

    This function is called by signal handlers to determine who made a change.
    The user is set in thread-local storage by AuditMiddlewareUser middleware.

    Returns:
        User: The authenticated user, or None if not available

    Notes:
        - Returns None if called outside HTTP request context (management tasks)
        - Returns None if user is AnonymousUser (unauthenticated)
        - Thread-safe: each thread has its own _thread_locals dict
    """
    return getattr(_thread_locals, 'user', None)


def set_current_user(user):
    """
    Store the currently authenticated user in thread-local storage.

    This function is called by AuditMiddlewareUser middleware at the start
    of each HTTP request, and cleared at the end.

    Args:
        user: The User instance to store, or None to clear

    Notes:
        - Called automatically by middleware; do not call directly
        - Thread-safe: each thread has its own _thread_locals dict
    """
    _thread_locals.user = user


def get_old_instance(model_class, pk):
    """
    Retrieve the saved old instance from thread-local storage.

    Before any model instance is saved, the pre_save signal captures the old
    state. This function retrieves that saved state for later comparison.

    Args:
        model_class: The Django model class (e.g., Grant, Expense)
        pk (int): The primary key of the instance

    Returns:
        Model instance: The saved old state, or None if not found

    Internal:
        Uses a composite key: f"{model_class.__name__}_{pk}"
    """
    old_instances = getattr(_thread_locals, 'old_instances', {})
    key = f"{model_class.__name__}_{pk}"
    return old_instances.get(key)


def set_old_instance(model_class, pk, instance):
    """
    Save the current instance state before modification.

    Called by pre_save signal handlers to capture the current state of an
    instance before it's saved, allowing later comparison with the new state.

    Args:
        model_class: The Django model class (e.g., Grant, Expense)
        pk (int): The primary key of the instance
        instance: The model instance to save, or None

    Notes:
        - Makes a deep copy to ensure independence from later changes
        - Uses composite key: f"{model_class.__name__}_{pk}"
        - Only called for updates (instance.pk must exist)
    """
    if not hasattr(_thread_locals, 'old_instances'):
        _thread_locals.old_instances = {}
    key = f"{model_class.__name__}_{pk}"
    _thread_locals.old_instances[key] = copy.deepcopy(instance) if instance else None


def clear_old_instance(model_class, pk):
    """
    Remove the saved instance state from thread-local storage.

    Called after processing by post_save signal to clean up temporary data.
    Prevents memory leaks in long-running processes.

    Args:
        model_class: The Django model class (e.g., Grant, Expense)
        pk (int): The primary key of the instance

    Notes:
        - Must match set_old_instance() composite key format
        - Safe to call multiple times or if key doesn't exist
    """
    if not hasattr(_thread_locals, 'old_instances'):
        return
    key = f"{model_class.__name__}_{pk}"
    _thread_locals.old_instances.pop(key, None)


class AuditMiddlewareUser:
    """
    Middleware to set current user in thread-local storage.

    This middleware is required for the audit system to function. It captures
    the authenticated user at the start of each HTTP request and stores it in
    thread-local storage, making it available to signal handlers.

    Lifecycle:
        1. __init__: Called once at server startup
        2. __call__: Called for every HTTP request
           - Extract request.user
           - Store in thread-local (_thread_locals.user)
           - Process request/response
           - Clear thread-local

    Installation:
        Add 'apps.audit.signals.AuditMiddlewareUser' to settings.py MIDDLEWARE,
        near the top but AFTER AuthenticationMiddleware.

    Example settings.py:
        MIDDLEWARE = [
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'apps.audit.signals.AuditMiddlewareUser',  # <-- Add here
            'django.contrib.messages.middleware.MessageMiddleware',
        ]

    Notes:
        - Gracefully handles unauthenticated/Anonymous users (logs None)
        - Thread-safe: each request thread has isolated storage
        - Cleanup happens automatically in __call__, preventing leaks
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract authenticated user or None if unauthenticated
        user = request.user if request.user.is_authenticated else None
        set_current_user(user)
        # Process the request
        response = self.get_response(request)
        # Clean up thread-local storage
        set_current_user(None)
        return response


def get_field_changes(instance, old_instance):
    """
    Compare old and new instances to detect what fields changed.

    This function performs field-by-field comparison between old and new states,
    returning only the fields that actually changed. It handles serialization
    of datetime fields and ignores auto-managed fields.

    Args:
        instance: The new/updated model instance
        old_instance: The old model instance (before changes), or None for creates

    Returns:
        dict: Field changes in format:
            {"field_name": {"old": "value1", "new": "value2"}, ...}
            Returns empty dict if no changes detected.

    Excluded Fields (not tracked):
        - id: Primary key (never changes)
        - created_at: Auto-generated on create
        - updated_at: Auto-updated on every save
        - yellow_alert_sent: Compliance-specific auto-field
        - Relation fields (ForeignKey, ManyToMany): Tracked separately if needed

    Serialization:
        - datetime / date objects: Converted to ISO format string
        - None values: Converted to string 'None'
        - All other types: Converted to string

    Usage:
        # This is called internally by signal handlers
        changes = get_field_changes(new_expense, old_expense)
        # changes = {
        #     'title': {'old': 'Office Supplies', 'new': 'Office Supplies - Updated'},
        #     'total_amount': {'old': '1000.00', 'new': '1200.00'}
        # }

    Notes:
        - Only called during UPDATE operations, not CREATE
        - If old_instance is None, all fields are treated as new (None -> value)
        - Handles AttributeError gracefully if accessing field fails
    """
    changes = {}

    # Get all field names except primary key and auto_now fields
    exclude_fields = {'id', 'created_at', 'updated_at', 'yellow_alert_sent'}

    for field in instance._meta.get_fields():
        # Skip relations and private fields
        if field.name in exclude_fields or field.many_to_one or field.many_to_many:
            continue

        try:
            if old_instance:
                old_value = getattr(old_instance, field.name, None)
            else:
                old_value = None
            new_value = getattr(instance, field.name, None)

            # Convert values to serializable format (datetime -> ISO string)
            if hasattr(old_value, 'isoformat'):  # datetime/date objects
                old_value = old_value.isoformat() if old_value else None
            if hasattr(new_value, 'isoformat'):
                new_value = new_value.isoformat() if new_value else None

            # Only record if value actually changed
            if old_value != new_value:
                changes[field.name] = {
                    'old': str(old_value) if old_value is not None else None,
                    'new': str(new_value) if new_value is not None else None,
                }
        except (AttributeError, ObjectDoesNotExist):
            # Skip fields that can't be accessed (e.g., deleted FK targets)
            pass

    return changes


@receiver(pre_save, sender=Grant)
def capture_grant_old_state(sender, instance, **kwargs):
    """Capture old instance before save for comparison"""
    if instance.pk:
        try:
            old_instance = Grant.objects.get(pk=instance.pk)
            set_old_instance(Grant, instance.pk, old_instance)
        except Grant.DoesNotExist:
            set_old_instance(Grant, instance.pk, None)


@receiver(post_save, sender=Grant)
def log_grant_change(sender, instance, created, **kwargs):
    """Log creation and updates to Grant model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        clear_old_instance(Grant, instance.pk)
        return

    if created:
        AuditLog.log_action(
            action=AuditLog.ACTION_CREATED,
            instance=instance,
            changed_by=user,
            changes={}
        )
    else:
        old_instance = get_old_instance(Grant, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=instance,
                changed_by=user,
                changes=changes
            )
    
    clear_old_instance(Grant, instance.pk)


@receiver(pre_save, sender=Expense)
def capture_expense_old_state(sender, instance, **kwargs):
    """Capture old instance before save for comparison"""
    if instance.pk:
        try:
            old_instance = Expense.objects.get(pk=instance.pk)
            set_old_instance(Expense, instance.pk, old_instance)
        except Expense.DoesNotExist:
            set_old_instance(Expense, instance.pk, None)


@receiver(post_save, sender=Expense)
def log_expense_change(sender, instance, created, **kwargs):
    """Log creation and updates to Expense model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        clear_old_instance(Expense, instance.pk)
        return

    if created:
        AuditLog.log_action(
            action=AuditLog.ACTION_CREATED,
            instance=instance,
            changed_by=user,
            changes={}
        )
    else:
        old_instance = get_old_instance(Expense, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=instance,
                changed_by=user,
                changes=changes
            )
    
    clear_old_instance(Expense, instance.pk)


@receiver(pre_save, sender=ExpenseAllocation)
def capture_expense_allocation_old_state(sender, instance, **kwargs):
    """Capture old instance before save for comparison"""
    if instance.pk:
        try:
            old_instance = ExpenseAllocation.objects.get(pk=instance.pk)
            set_old_instance(ExpenseAllocation, instance.pk, old_instance)
        except ExpenseAllocation.DoesNotExist:
            set_old_instance(ExpenseAllocation, instance.pk, None)


@receiver(post_save, sender=ExpenseAllocation)
def log_expense_allocation_change(sender, instance, created, **kwargs):
    """Log creation and updates to ExpenseAllocation model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        clear_old_instance(ExpenseAllocation, instance.pk)
        return

    if created:
        AuditLog.log_action(
            action=AuditLog.ACTION_CREATED,
            instance=instance,
            changed_by=user,
            changes={}
        )
    else:
        old_instance = get_old_instance(ExpenseAllocation, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=instance,
                changed_by=user,
                changes=changes
            )
    
    clear_old_instance(ExpenseAllocation, instance.pk)


@receiver(pre_save, sender=ComplianceDocument)
def capture_compliance_document_old_state(sender, instance, **kwargs):
    """Capture old instance before save for comparison"""
    if instance.pk:
        try:
            old_instance = ComplianceDocument.objects.get(pk=instance.pk)
            set_old_instance(ComplianceDocument, instance.pk, old_instance)
        except ComplianceDocument.DoesNotExist:
            set_old_instance(ComplianceDocument, instance.pk, None)


@receiver(post_save, sender=ComplianceDocument)
def log_compliance_document_change(sender, instance, created, **kwargs):
    """Log creation and updates to ComplianceDocument model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        clear_old_instance(ComplianceDocument, instance.pk)
        return

    if created:
        AuditLog.log_action(
            action=AuditLog.ACTION_CREATED,
            instance=instance,
            changed_by=user,
            changes={}
        )
    else:
        old_instance = get_old_instance(ComplianceDocument, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=instance,
                changed_by=user,
                changes=changes
            )
    
    clear_old_instance(ComplianceDocument, instance.pk)


@receiver(post_delete, sender=Grant)
def log_grant_deletion(sender, instance, **kwargs):
    """Log deletion of Grant model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        return

    AuditLog.log_action(
        action=AuditLog.ACTION_DELETED,
        instance=instance,
        changed_by=user,
        changes={},
    )


@receiver(post_delete, sender=Expense)
def log_expense_deletion(sender, instance, **kwargs):
    """Log deletion of Expense model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        return

    AuditLog.log_action(
        action=AuditLog.ACTION_DELETED,
        instance=instance,
        changed_by=user,
        changes={},
    )


@receiver(post_delete, sender=ExpenseAllocation)
def log_expense_allocation_deletion(sender, instance, **kwargs):
    """Log deletion of ExpenseAllocation model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        return

    AuditLog.log_action(
        action=AuditLog.ACTION_DELETED,
        instance=instance,
        changed_by=user,
        changes={},
    )


@receiver(post_delete, sender=ComplianceDocument)
def log_compliance_document_deletion(sender, instance, **kwargs):
    """Log deletion of ComplianceDocument model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        return

    AuditLog.log_action(
        action=AuditLog.ACTION_DELETED,
        instance=instance,
        changed_by=user,
        changes={},
    )


# Donor model signals
@receiver(pre_save, sender=Donor)
def capture_donor_old_state(sender, instance, **kwargs):
    """Capture old instance before save for comparison"""
    if instance.pk:
        try:
            old_instance = Donor.objects.get(pk=instance.pk)
            set_old_instance(Donor, instance.pk, old_instance)
        except Donor.DoesNotExist:
            set_old_instance(Donor, instance.pk, None)


@receiver(post_save, sender=Donor)
def log_donor_change(sender, instance, created, **kwargs):
    """Log creation and updates to Donor model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        clear_old_instance(Donor, instance.pk)
        return

    if created:
        AuditLog.log_action(
            action=AuditLog.ACTION_CREATED,
            instance=instance,
            changed_by=user,
            changes={}
        )
    else:
        old_instance = get_old_instance(Donor, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(
                action=AuditLog.ACTION_UPDATED,
                instance=instance,
                changed_by=user,
                changes=changes
            )
    
    clear_old_instance(Donor, instance.pk)


@receiver(post_delete, sender=Donor)
def log_donor_deletion(sender, instance, **kwargs):
    """Log deletion of Donor model"""
    user = get_current_user()

    if not user or isinstance(user, AnonymousUser):
        return

    AuditLog.log_action(
        action=AuditLog.ACTION_DELETED,
        instance=instance,
        changed_by=user,
        changes={},
    )
