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
    """Send email alert for a single ComplianceDocument identified by id.

    This task updates `yellow_alert_sent` on success so the system does not
    re-send alerts for the same document.
    """
    try:
        doc = ComplianceDocument.objects.get(id=doc_id)
    except ComplianceDocument.DoesNotExist:
        return False

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
        raise self.retry(exc=exc, countdown=60, max_retries=3)


@shared_task
def send_compliance_alerts():
    """Find yellow documents that haven't had an alert sent and enqueue tasks."""
    today = timezone.localdate()
    window_end = today + timedelta(days=180)

    # `status` is a Python @property (not a DB field). Compute "yellow"
    # documents by filtering expiry_date within the next 180 days and
    # excluding already-expired documents.
    yellow_qs = ComplianceDocument.objects.filter(
        yellow_alert_sent__isnull=True,
        expiry_date__gte=today,
        expiry_date__lte=window_end,
    )

    for doc in yellow_qs:
        send_yellow_alert_email_task.delay(doc.id)

    return yellow_qs.count()
