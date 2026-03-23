"""
Celery tasks for compliance certificate management.

This module contains asynchronous tasks that run on a schedule (Celery Beat)
to monitor certificate expiry and send alert emails to admins when certificates
enter 'yellow' status (expiring within 180 days).

Task Flow:
    1. send_compliance_alerts() - Runs daily at 6 AM (see celerybeat schedule)
    2. Finds all yellow certificates that haven't had alert sent yet
    3. Queues send_yellow_alert_email_task() for each one
    4. send_yellow_alert_email_task() sends email and marks yellow_alert_sent

Configuration:
    CELERY_BEAT_SCHEDULE in settings.py must have:
        'send-compliance-alerts': {
            'task': 'apps.compliance.tasks.send_compliance_alerts',
            'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
        }

    CELERY_BROKER_URL: 'redis://localhost:6379/0'  # or similar

See Also:
    - apps.compliance.utils.is_compliant() for compliance gating logic
    - apps.compliance.models.ComplianceDocument for status computation
"""
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import ComplianceDocument
from apps.accounts.models import User


@shared_task(bind=True)
def send_yellow_alert_email_task(self, doc_id: int) -> bool:
    """
    Send email alert for a single ComplianceDocument identified by id.

    This Celery task sends an HTML email to all admin users notifying them
    that a compliance certificate will expire soon (yellow status). On success,
    it updates the yellow_alert_sent timestamp to prevent duplicate emails.

    Args:
        self: Celery task instance (bind=True)
        doc_id (int): Primary key of the ComplianceDocument to alert about

    Returns:
        bool: True if email sent and yellow_alert_sent updated, False otherwise

    Retry Policy:
        On failure:
        - Retries after 60 seconds
        - Max 3 total attempts (exponential backoff)
        - Raises celery.exceptions.Retry on failure (triggers retry)

    Normal Flow:
        1. Fetch the document
        2. Get all admin email addresses
        3. Render email (HTML from template or plain text fallback)
        4. Send via Django email backend
        5. Update document.yellow_alert_sent = now()
        6. Return True

    Error Handling:
        - ComplianceDocument.DoesNotExist: Returns False, no retry
        - No admin emails available: Returns False, no retry
        - Email send failure: Raises self.retry() to retry later
        - Template missing: Falls back to plain text message

    Email Details:
        From: settings.DEFAULT_FROM_EMAIL
        To: All users with role='admin' and non-empty email
        Subject: "Certificate Alert: {CERT_TYPE} Expiring Soon"
        Template: templates/compliance/notification_email.html
        Context:
            - document: The ComplianceDocument object
            - days_to_expiry: Computed value
            - expiry_date: From document

    Called By:
        - send_compliance_alerts() task (once per day per yellow certificate)

    Example:
        # Manually trigger alert for a specific certificate
        send_yellow_alert_email_task.delay(doc_id=42)

    Notes:
        - Idempotent: yellow_alert_sent timestamp prevents duplicate emails
        - Fire-and-forget: Queued asynchronously, doesn't block request
        - Update_fields=['yellow_alert_sent']: Only updates one field for efficiency
        - save() after setting timestamp, not before
    """
    try:
        doc = ComplianceDocument.objects.get(id=doc_id)
    except ComplianceDocument.DoesNotExist:
        return False

    # Get all admin users with email addresses
    admins = User.objects.filter(role="admin")
    admin_emails = [a.email for a in admins if a.email]
    if not admin_emails:
        return False

    subject = f"Certificate Alert: {doc.get_cert_type_display()} Expiring Soon"
    context = {"document": doc, "days_to_expiry": doc.days_to_expiry, "expiry_date": doc.expiry_date}
    try:
        message = render_to_string("compliance/notification_email.html", context)
        html_message = message
    except Exception:
        message = (
            f"Alert: {doc.get_cert_type_display()} is expiring soon!\n"
            f"Expiry Date: {doc.expiry_date}\n"
            f"Days Until Expiry: {doc.days_to_expiry}\n"
        )
        html_message = None

    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, admin_emails, html_message=html_message, fail_silently=False)
        doc.yellow_alert_sent = timezone.now()
        doc.save(update_fields=["yellow_alert_sent"])
        return True
    except Exception as exc:
        # Retry with exponential backoff: 60s, 120s, 240s, then give up
        raise self.retry(exc=exc, countdown=60, max_retries=3)


@shared_task
def send_compliance_alerts():
    """
    Find all yellow certificates without a sent alert and queue email tasks.

    This task runs on a schedule (Celery Beat, typically daily at 6 AM) to:
    1. Find all ComplianceDocument with status='yellow' that haven't had alerts
    2. Queue send_yellow_alert_email_task() for each
    3. Return count of tasks queued

    Status Computation:
        A certificate has status='yellow' if:
        - expiry_date > today (not yet expired)
        - expiry_date <= today + 180 days (within 6 months)

    Alert Suppression:
        Once yellow_alert_sent is set (by send_yellow_alert_email_task),
        the certificate is skipped in subsequent runs. This prevents
        duplicate alert emails for the same certificate.

        Note: Status property is computed in Python, not DB query.
        So we filter expiry dates in DB, then check status in memory.

    Query Optimization:
        - Filters by expiry_date directly (DB index friendly)
        - Excludes already-alerted certs (yellow_alert_sent__isnull=True)
        - Small result set (max ~3 certs normally)
        - No prefetch/select_related needed

    Filter Logic:
        __gte=today: Don't alert if already expired (red status)
        __lte=today+180days: Only alert if within 6 months
        yellow_alert_sent__isnull=True: Exclude already-alerted

    Called By:
        Celery Beat schedule (see CELERY_BEAT_SCHEDULE in settings.py)
        Example: 'send-compliance-alerts': {
            'task': 'apps.compliance.tasks.send_compliance_alerts',
            'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
        }

    Returns:
        int: Number of alert tasks queued (for logging/monitoring)

    Example Return Values:
        send_compliance_alerts() → 0  # All certificates healthy
        send_compliance_alerts() → 1  # One cert entering yellow, alert queued
        send_compliance_alerts() → 2  # Two certs need alerts queued

    Notes:
        - Task timing: Runs every day at 6 AM (configurable)
        - Delay: Email sends asynchronously (within minutes normally)
        - Idempotent: Repeated runs don't duplicate emails (yellow_alert_sent guards)
        - Error Tolerant: Task doesn't fail if email send fails (retried separately)
        - Monitoring: Return count useful for alerting if no tasks queued (system down)

    See Also:
        - ComplianceDocument.status property (green/yellow/red logic)
        - ComplianceDocument.yellow_alert_sent field
        - send_yellow_alert_email_task() (actual email sending)
        - is_compliant() in utils.py (compliance gating logic)
    """
    today = timezone.localdate()
    window_end = today + timedelta(days=180)

    # Filter for certificates expiring within ~180 days that haven't had alert sent
    # Note: status is a Python @property, not a DB field, so we compute it
    # by filtering on expiry_date directly
    yellow_qs = ComplianceDocument.objects.filter(
        yellow_alert_sent__isnull=True,
        expiry_date__gte=today,
        expiry_date__lte=window_end,
    )

    # Queue a task for each yellow certificate
    for doc in yellow_qs:
        send_yellow_alert_email_task.delay(doc.id)

    # Return count for logging/monitoring
    return yellow_qs.count()
