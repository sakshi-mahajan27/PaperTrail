from django.contrib import admin
from .models import ComplianceDocument


@admin.register(ComplianceDocument)
class ComplianceDocumentAdmin(admin.ModelAdmin):
    """
    Django admin interface for Compliance Certificate documents.

    Allows admins to view and edit compliance certificates (FCRA, 80G, 12A).
    Edit fields include: issue_date, expiry_date, and cert_type.
    Uploaded_by, uploaded_at, updated_at are read-only (auto-managed).

    List Display (Columns):
        - cert_type: Certificate type (FCRA/80G/12A)
        - issue_date: Date certificate was issued
        - expiry_date: Date certificate expires
        - status: Current status (green/yellow/red) - @property, color-coded
        - uploaded_by: User who uploaded certificate (FK to User)

    List Filters (Right Sidebar):
        None currently—could add cert_type or status filters for large datasets

    Search Fields:
        None currently—could add cert_type or uploaded_by__username

    Read-Only Fields:
        - uploaded_at: Auto set when document created (immutable)
        - updated_at: Auto-refreshed on every save (immutable for user)
        - uploaded_by: Set from request.user (immutable for user)

    Editable Fields:
        - cert_type: Certificate type (FCRA/80G/12A dropdown)
        - issue_date: Date issued (date picker)
        - expiry_date: Date expires (date picker)
        - file field: Upload PDF/document

    Status Display:
        Shows computed @property status as:
        - GREEN: > 180 days to expiry
        - YELLOW: ≤ 180 days to expiry
        - RED: Expired (expiry_date < today)
        Color-coded in list view (CSS classes/styling).

    Use Cases:
        - View: Click cert_type to see details
        - Upload: Upload new certificate (handled in web form, not admin)
        - Edit: Change expiry_date if correcting mistake
        - Filter: Would help find expiring certificates
        - Monitor: Check status colors at a glance

    Business Context:
        Three certificates required for NGO compliance:
        - FCRA: For international donations
        - 80G: For tax-deductible donations
        - 12A: For income-tax exemption

        Admin views status color-coded:
        - Red: URGENT - renewal needed immediately
        - Yellow: ACTION NEEDED - renew within 3-6 months
        - Green: OK - no action needed yet

    Validation:
        - expiry_date auto-validates (date field)
        - status computed from expiry_date vs today
        - yellow_alert_sent auto-managed by Celery tasks

    Permissions:
        - Edit: Allowed (but form only used for corrections)
        - Delete: Allowed (but discouraged—better to upload new)
        - Add: Allowed (but web form preferred for uploaded_by tracking)

    Audit Trail:
        Changes logged by signals (expiry_date changes tracked).
        Example: "expiry_date: 2024-12-31 → 2025-12-31"

    Related Views:
        - document_upload: Web form for uploading new certificates
        - document_edit: Web form for updating certificate
        - compliance_status_report: Admin views all statuses
        - is_compliant(): Checks if any RED status exists

    Notes:
        - No inlines (ComplianceDocument is a simple model)
        - Status is @property (not stored, computed on-the-fly)
        - yellow_alert_sent is Datetime field tracking last yellow email
        - file field stores actual certificate document (PDF/etc)
    """
    list_display = ["cert_type", "issue_date", "expiry_date", "status", "uploaded_by"]
    readonly_fields = ["uploaded_at", "updated_at", "uploaded_by"]
