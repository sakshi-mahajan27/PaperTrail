from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ComplianceDocument
from .utils import send_yellow_alert_email


@receiver(post_save, sender=ComplianceDocument)
def send_expiry_alert(sender, instance, created, **kwargs):
    """
    Signal handler to send email alert when a compliance document enters yellow status.
    Only sends once per document (tracked by yellow_alert_sent field).
    """
    # Check if document is in yellow status
    if instance.status == "yellow":
        # Only send if we haven't already sent an alert for this document
        if not instance.yellow_alert_sent:
            # Send the email
            if send_yellow_alert_email(instance):
                # Mark that we've sent the alert
                instance.yellow_alert_sent = timezone.now()
                # Save without triggering the signal again
                ComplianceDocument.objects.filter(pk=instance.pk).update(
                    yellow_alert_sent=instance.yellow_alert_sent
                )
