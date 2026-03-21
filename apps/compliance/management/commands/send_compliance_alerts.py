from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.compliance.models import ComplianceDocument
from apps.compliance.tasks import send_yellow_alert_email_task


class Command(BaseCommand):
    help = "Enqueue compliance expiration alert tasks for documents in yellow status"

    def handle(self, *args, **options):
        today = timezone.localdate()
        threshold = today + timedelta(days=180)

        yellow_docs = ComplianceDocument.objects.filter(
            yellow_alert_sent__isnull=True,
            expiry_date__gte=today,
            expiry_date__lte=threshold,
        )

        enqueued = 0
        for doc in yellow_docs:
            send_yellow_alert_email_task.delay(doc.id)
            enqueued += 1

        self.stdout.write(self.style.SUCCESS(f"Enqueued {enqueued} alert tasks"))
