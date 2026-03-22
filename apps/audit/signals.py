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
    """Get the current user from thread-local storage"""
    return getattr(_thread_locals, 'user', None)


def set_current_user(user):
    """Set the current user in thread-local storage"""
    _thread_locals.user = user


def get_old_instance(model_class, pk):
    """Get old instance from thread-local storage"""
    old_instances = getattr(_thread_locals, 'old_instances', {})
    key = f"{model_class.__name__}_{pk}"
    return old_instances.get(key)


def set_old_instance(model_class, pk, instance):
    """Store old instance in thread-local storage before save"""
    if not hasattr(_thread_locals, 'old_instances'):
        _thread_locals.old_instances = {}
    key = f"{model_class.__name__}_{pk}"
    _thread_locals.old_instances[key] = copy.deepcopy(instance) if instance else None


def clear_old_instance(model_class, pk):
    """Clear old instance from thread-local storage after processing"""
    if not hasattr(_thread_locals, 'old_instances'):
        return
    key = f"{model_class.__name__}_{pk}"
    _thread_locals.old_instances.pop(key, None)


class AuditMiddlewareUser:
    """
    Middleware to set current user in thread-local storage.
    Add this to your middleware list in settings.py
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        set_current_user(user)
        response = self.get_response(request)
        set_current_user(None)
        return response


def get_field_changes(instance, old_instance):
    """
    Compare old and new instances to detect what fields changed.
    Returns a dict of {field_name: {'old': old_value, 'new': new_value}}
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

            # Convert values to serializable format
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
