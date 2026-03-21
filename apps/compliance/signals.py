from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ComplianceDocument
from .utils import send_yellow_alert_email

@receiver(pre_save, sender=ComplianceDocument)
def cache_previous_status(sender, instance, **kwargs):
    """Cache the previous status on the instance so post_save can detect transitions."""
    if instance.pk:
        try:
            prev = ComplianceDocument.objects.get(pk=instance.pk)
            instance._prev_status = prev.status
        except ComplianceDocument.DoesNotExist:
            instance._prev_status = None
    else:
        instance._prev_status = None


@receiver(post_save, sender=ComplianceDocument)
def send_expiry_alert(sender, instance, created, **kwargs):
    """
    Send email when a document becomes 'yellow' (Expiring Soon).

    Rules:
    - If the document was just created and is yellow, send the alert.
    - If the document transitioned from a non-yellow status to yellow, send the alert
      again even if a prior alert timestamp exists.
    - Otherwise, do not resend.
    """
    prev_status = getattr(instance, "_prev_status", None)

    # If document is currently yellow and it either was just created
    # or transitioned from a different status, send the alert.
    if instance.status == "yellow" and (created or prev_status != "yellow"):
        if send_yellow_alert_email(instance):
            ComplianceDocument.objects.filter(pk=instance.pk).update(
                yellow_alert_sent=timezone.now()
            )
