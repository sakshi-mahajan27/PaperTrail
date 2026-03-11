"""
Django signals that automatically write AuditLog entries whenever
Expense, Grant, Donor, or ComplianceDocument instances are saved or deleted.

The current user is injected via AuditMiddleware (see middleware.py).
"""
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.expenses.models import Expense
from apps.grants.models import Grant
from apps.donors.models import Donor
from apps.compliance.models import ComplianceDocument
from .utils import log_action, get_current_user, model_to_dict_simple
from .models import AuditLog

# ── helpers ──────────────────────────────────────────────────────────────────

def _prev(instance):
    """Fetch the current DB state before the save."""
    try:
        return model_to_dict_simple(instance.__class__.objects.get(pk=instance.pk))
    except instance.__class__.DoesNotExist:
        return None


# ── Expense ───────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Expense)
def expense_pre_save(sender, instance, **kwargs):
    instance._audit_prev = _prev(instance)


@receiver(post_save, sender=Expense)
def expense_post_save(sender, instance, created, **kwargs):
    action = AuditLog.ACTION_CREATED if created else AuditLog.ACTION_UPDATED
    log_action(get_current_user(), action, instance, prev_value=getattr(instance, "_audit_prev", None))


@receiver(pre_delete, sender=Expense)
def expense_pre_delete(sender, instance, **kwargs):
    log_action(get_current_user(), AuditLog.ACTION_DELETED, instance, prev_value=model_to_dict_simple(instance))


# ── Grant ─────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Grant)
def grant_pre_save(sender, instance, **kwargs):
    instance._audit_prev = _prev(instance)


@receiver(post_save, sender=Grant)
def grant_post_save(sender, instance, created, **kwargs):
    action = AuditLog.ACTION_CREATED if created else AuditLog.ACTION_UPDATED
    log_action(get_current_user(), action, instance, prev_value=getattr(instance, "_audit_prev", None))


@receiver(pre_delete, sender=Grant)
def grant_pre_delete(sender, instance, **kwargs):
    log_action(get_current_user(), AuditLog.ACTION_DELETED, instance, prev_value=model_to_dict_simple(instance))


# ── Donor ─────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Donor)
def donor_pre_save(sender, instance, **kwargs):
    instance._audit_prev = _prev(instance)


@receiver(post_save, sender=Donor)
def donor_post_save(sender, instance, created, **kwargs):
    action = AuditLog.ACTION_CREATED if created else AuditLog.ACTION_UPDATED
    log_action(get_current_user(), action, instance, prev_value=getattr(instance, "_audit_prev", None))


@receiver(pre_delete, sender=Donor)
def donor_pre_delete(sender, instance, **kwargs):
    log_action(get_current_user(), AuditLog.ACTION_DELETED, instance, prev_value=model_to_dict_simple(instance))


# ── ComplianceDocument ────────────────────────────────────────────────────────

@receiver(pre_save, sender=ComplianceDocument)
def compliance_pre_save(sender, instance, **kwargs):
    instance._audit_prev = _prev(instance)


@receiver(post_save, sender=ComplianceDocument)
def compliance_post_save(sender, instance, created, **kwargs):
    action = AuditLog.ACTION_CREATED if created else AuditLog.ACTION_UPDATED
    log_action(get_current_user(), action, instance, prev_value=getattr(instance, "_audit_prev", None))


@receiver(pre_delete, sender=ComplianceDocument)
def compliance_pre_delete(sender, instance, **kwargs):
    log_action(get_current_user(), AuditLog.ACTION_DELETED, instance, prev_value=model_to_dict_simple(instance))
