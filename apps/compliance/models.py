from django.db import models
from django.utils import timezone
from apps.accounts.models import User


class ComplianceDocument(models.Model):
    """
    Regulatory compliance certificates for NGO operation.

    This model tracks the three mandatory certifications required by Indian NGOs
    to operate legally and accept donations:
    - FCRA (Foreign Contribution Regulation Act): Required to accept foreign donations
    - 80G: Income Tax exemption certificate; enables donor tax deductions
    - 12A: Income Tax exemption; allows tax-free operations

    Business Purpose:
        All three certificates must be valid (not expired) for expenses and grants
        to be created. The is_compliant() utility in utils.py uses these documents
        to enforce a "compliance gate" on all financial operations.

    Status Calculation (via @property):
        'green' (valid):        expiry_date > today AND days_to_expiry > 180
        'yellow' (expiring):    expiry_date > today AND days_to_expiry <= 180
        'red' (expired):        expiry_date <= today

    This tri-color system enables:
        - Red: Block all expenses/grants (hard compliance gate)
        - Yellow: Allow ops but send alert email to admins (soft warning)
        - Green: Full normal operation

    Fields:
        cert_type (str): One of 'FCRA', '80G', or '12A'.
            unique=True: Only one certificate per type can exist.
            Choices are defined in CERT_TYPE_CHOICES.

        issue_date (date): When the certificate was issued.
            Typically from the agency (Income Tax Directorate, MHA).

        expiry_date (date): When the certificate expires.
            Used to compute status property.
            Critical field: expenses cannot be created if ANY cert is expired.

        certificate_file (FileField): Uploaded PDF/image of the certificate.
            Stored in media/compliance/ directory.
            Serves as proof for audits.

        notes (str): Optional notes, e.g., renewal plan, exemption conditions.

        uploaded_by (ForeignKey): Admin user who uploaded this certificate.
            Foreign key to User model (SET_NULL on user deletion).
            Enables accountability: who uploaded what and when.

        uploaded_at (datetime): When the document was first uploaded.
            auto_now_add=True: Set on creation, never changes.
            Useful for tracking certificate lifecycle.

        updated_at (datetime): When the document was last modified.
            auto_now=True: Updated on every save.
            Useful for change tracking.

        yellow_alert_sent (datetime, nullable): When yellow alert email was sent.
            Null if no yellow alert sent yet.
            Prevents duplicate alert emails for the same certificate.
            Set by send_yellow_alert_email_task (Celery task in tasks.py).

    Metadata:
        ordering: By cert_type (FCRA, 80G, 12A alphabetically)
        verbose_name: "Compliance Document" (singular)

    Example Lifecycle:
        1. Admin uploads FCRA certificate (uploaded_at=now, yellow_alert_sent=NULL)
        2. Compliance status computed:
           - Issue: 2023-03-01, Expiry: 2028-03-01
           - Today: 2025-03-23 (current date)
           - Days to expiry: ~1,073 days
           - Status: 'green' (> 180 days)
        3. Celery task checks daily for yellow certs
        4. When ~6 months out, status='yellow'
        5. Alert email sent, yellow_alert_sent=now
        6. On expiry_date, status='red'
        7. Block all expenses/grants until renewed

    Query Examples:
        # Find all valid certificates
        valid = ComplianceDocument.objects.filter(
            expiry_date__gte=timezone.localdate()
        )

        # Find expiring soon (yellow)
        from datetime import timedelta
        soon = ComplianceDocument.objects.filter(
            expiry_date__gte=timezone.localdate(),
            expiry_date__lte=timezone.localdate() + timedelta(days=180)
        )

        # Find specific cert type
        fcra = ComplianceDocument.objects.get(cert_type='FCRA')

    Security & Compliance Notes:
        - File uploaded is not validated (admin responsibility)
        - Expiry dates are trust-based (not verified against agency database)
        - Yellow alert system ensures proactive renewal process
        - Audit trail created for every change via AuditLog (signals.py)

    Performance Notes:
        - status property is computed on access (not cached)
        - In dashboard, status is computed via Python loop (not DB queryset)
        - For high-volume scenarios, could cache status in DB field
        - All queries are simple (only ~3 certs exist in typical setup)
    """

    FCRA = "FCRA"
    G80 = "80G"
    A12 = "12A"

    CERT_TYPE_CHOICES = [
        (FCRA, "FCRA Certificate"),
        (G80, "80G Certificate"),
        (A12, "12A Certificate"),
    ]

    cert_type = models.CharField(
        max_length=10,
        choices=CERT_TYPE_CHOICES,
        unique=True,
        help_text="Type of compliance certificate. Only one of each type can exist."
    )
    issue_date = models.DateField(
        help_text="Date when the certificate was issued by the authority"
    )
    expiry_date = models.DateField(
        help_text="Date when the certificate expires. Critical for compliance gating."
    )
    certificate_file = models.FileField(
        upload_to="compliance/",
        help_text="PDF or image file of the certificate"
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about renewal plans, exemption conditions, etc."
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="compliance_docs",
        help_text="Admin who uploaded this certificate"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Automatically set when first uploaded. Cannot be changed."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Updated every time the document is modified"
    )
    yellow_alert_sent = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the yellow 'expiring soon' alert email was sent. Prevents duplicate emails."
    )

    class Meta:
        ordering = ["cert_type"]
        verbose_name = "Compliance Document"

    def __str__(self):
        return f"{self.get_cert_type_display()} (expires {self.expiry_date})"

    @property
    def status(self):
        """
        Compute the current compliance status of this certificate.

        Returns:
            str: One of 'green', 'yellow', or 'red'

        Status Logic:
            'red':    Certificate has expired (expiry_date < today)
                      → expenses/grants CANNOT be created
            'yellow': Certificate will expire soon (≤ 180 days remaining)
                      → expenses/grants CAN be created, but alertemail sent to admins
            'green':  Certificate is valid with > 180 days remaining
                      → expenses/grants can be created normally

        Implementation Notes:
            - Uses timezone.localdate() for date comparison (respects USE_TZ setting)
            - 180-day window = ~6 months (reasonable renewal lead time)
            - Computed on every access (not cached)

        Used By:
            - is_compliant() in utils.py (checks if ANY cert is red)
            - dashboard_view in accounts/views.py (counts status breakdown)
            - compliance_status_report in reports/views.py
        """
        today = timezone.localdate()
        if self.expiry_date < today:
            return "red"
        delta = (self.expiry_date - today).days
        if delta <= 180:
            return "yellow"
        return "green"

    @property
    def status_label(self):
        """
        Return human-readable label for the current status.

        Returns:
            str: One of 'Valid', 'Expiring Soon', '' (empty for unknown)

        Mapping:
            'green'  → 'Valid'
            'yellow' → 'Expiring Soon'
            'red'    → 'Expired'

        Used By:
            - Templates for display
            - Alert emails (send_yellow_alert_email in utils.py)
        """
        return {"green": "Valid", "yellow": "Expiring Soon", "red": "Expired"}.get(self.status, "")

    @property
    def days_to_expiry(self):
        """
        Calculate days remaining until expiration.

        Returns:
            int: Number of days from today to expiry_date
            Can be negative if certificate has already expired

        Examples:
            - Days to expiry: 500 days (green status)
            - Days to expiry: 90 days (yellow status)
            - Days to expiry: -10 days (red status, already expired)

        Used By:
            - Alert emails (days_to_expiry context variable)
            - Dashboard (not currently used but useful for templates)
        """
        return (self.expiry_date - timezone.localdate()).days
