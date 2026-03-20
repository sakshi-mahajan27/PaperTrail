from django.db import models
from django.utils import timezone
from apps.accounts.models import User


class ComplianceDocument(models.Model):
    FCRA = "FCRA"
    G80 = "80G"
    A12 = "12A"

    CERT_TYPE_CHOICES = [
        (FCRA, "FCRA Certificate"),
        (G80, "80G Certificate"),
        (A12, "12A Certificate"),
    ]

    cert_type = models.CharField(max_length=10, choices=CERT_TYPE_CHOICES, unique=True)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    certificate_file = models.FileField(upload_to="compliance/")
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="compliance_docs"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    yellow_alert_sent = models.DateTimeField(null=True, blank=True, help_text="When the yellow 'expiring soon' alert was sent")

    class Meta:
        ordering = ["cert_type"]
        verbose_name = "Compliance Document"

    def __str__(self):
        return f"{self.get_cert_type_display()} (expires {self.expiry_date})"

    @property
    def status(self):
        today = timezone.localdate()
        if self.expiry_date < today:
            return "red"
        delta = (self.expiry_date - today).days
        if delta <= 180:
            return "yellow"
        return "green"

    @property
    def status_label(self):
        return {"green": "Valid", "yellow": "Expiring Soon", "red": "Expired"}.get(self.status, "")

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days
