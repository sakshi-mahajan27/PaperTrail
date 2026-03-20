from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.compliance.models import ComplianceDocument
from apps.compliance.utils import send_yellow_alert_email


class Command(BaseCommand):
    help = "Check compliance documents and send expiration alerts for documents in yellow status"

    def handle(self, *args, **options):
        # Get all documents in yellow status that haven't had an alert sent yet
        yellow_docs = ComplianceDocument.objects.filter(
            yellow_alert_sent__isnull=True
        )
        
        alert_count = 0
        for doc in yellow_docs:
            # Double-check the status is actually yellow
            if doc.status == "yellow":
                if send_yellow_alert_email(doc):
                    doc.yellow_alert_sent = timezone.now()
                    doc.save()
                    alert_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Alert sent for {doc.get_cert_type_display()}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to send alert for {doc.get_cert_type_display()}"
                        )
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f"Sent {alert_count} expiration alerts")
        )
