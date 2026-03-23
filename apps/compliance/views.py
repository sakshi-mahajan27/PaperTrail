from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import ComplianceDocument
from .forms import ComplianceDocumentForm
from apps.accounts.decorators import role_required


@login_required
@role_required("admin")
def document_list(request):
    """
    Display a list of all compliance certificates.

    Admin-only view showing the three NGO compliance documents (FCRA, 80G, 12A),
    their status (green/yellow/red), and expiry information. This is the main
    compliance management interface.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Response:
        200 HTML table of compliance documents with status indicators

    Template Used:
        compliance/document_list.html

    Context Variables:
        docs (QuerySet): All ComplianceDocument objects, ordered by cert_type

    Data Rendering:
        - For each document, displays:
            * Certificate type (FCRA, 80G, 12A)
            * Issue date
            * Expiry date
            * Status badge (green/yellow/red)
            * Days until expiry
            * Edit and delete buttons (admin only)

    Business Logic:
        Each document's status is computed via @property:
        - 'red': Expired → blocks all expenses/grants
        - 'yellow': Expiring soon (≤180 days) → warning emails sent
        - 'green': Valid with >180 days remaining → normal operations

    Access Control:
        - Only admins can view this page
        - Non-admins redirected to dashboard with error message

    Notes:
        - Exactly 3 certificates should exist (one per type)
        - If any are missing or expired, is_compliant() returns False
        - Soft-delete not used; certificates are never deleted
        - Audit logs created for every upload/edit (signals.py)
    """
    docs = ComplianceDocument.objects.all()
    return render(request, "compliance/document_list.html", {"docs": docs})


@login_required
@role_required("admin")
def document_upload(request):
    """
    Upload a new compliance certificate.

    Admin-only view for registering a new compliance certificate in the system.
    Each certificate type (FCRA, 80G, 12A) can only be uploaded once; subsequent
    uploads replace the previous certificate.

    Request Method:
        GET: Display empty form
        POST: Upload and save new certificate

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Form Used:
        ComplianceDocumentForm

    Response:
        - 200 Display form on GET
        - 302 Redirect to document_list on success
        - 200 Display form with validation errors on failed POST

    Template Used:
        compliance/document_form.html

    Context Variables:
        form: ComplianceDocumentForm instance
        title: "Upload Certificate"

    Form Fields:
        - cert_type: Choose FCRA, 80G, or 12A
        - issue_date: Date certificate was issued
        - expiry_date: Date certificate expires (critical)
        - certificate_file: PDF or image file
        - notes: Optional renewal reminders

    Success Flow:
        1. Admin fills form with certificate details
        2. Selects file (PDF/image)
        3. Submits POST
        4. Form validated (expiry > issue date)
        5. Certificate saved to database
        6. uploaded_by set to current admin (request.user)
        7. Message: "{CERT_TYPE} uploaded successfully."
        8. Redirect to document_list

    Error Handling:
        - If cert_type already exists: Model UPDATE instead (unique field)
        - If expiry <= issue date: ValidationError from form.clean()
        - If file upload fails: Handled by Django file upload middleware

    Business Impact:
        - Once uploaded, certificate status is computed automatically
        - If status becomes 'red', expenses/grants are immediately blocked
        - If status becomes 'yellow', Celery task sends alert emails

    Notes:
        - File is stored in MEDIA_ROOT/compliance/ directory
        - uploaded_by tracks who uploaded for audit trail
        - yellow_alert_sent initially NULL (set when alert email sent)
        - Audit log created via post_save signal (signals.py)
    """
    form = ComplianceDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        doc.uploaded_by = request.user
        doc.save()
        messages.success(request, f"{doc.get_cert_type_display()} uploaded successfully.")
        return redirect("compliance:document_list")
    return render(request, "compliance/document_form.html", {"form": form, "title": "Upload Certificate"})


@login_required
@role_required("admin")
def document_edit(request, pk):
    """
    Edit an existing compliance certificate.

    Admin-only view for updating certificate details like issue date, expiry date,
    and renewal notes. The cert_type cannot be changed (enforced by form).

    Request Method:
        GET: Display pre-populated form
        POST: Update certificate details

    Path Parameters:
        pk (int): Primary key of ComplianceDocument to edit

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Form Used:
        ComplianceDocumentForm

    Response:
        - 200 Display form on GET
        - 302 Redirect to document_list on success
        - 200 Display form with errors on failed POST
        - 404 If certificate with given pk doesn't exist

    Template Used:
        compliance/document_form.html

    Context Variables:
        form: ComplianceDocumentForm instance, pre-filled with current data
        title: "Edit Certificate"
        object: The ComplianceDocument being edited

    Editable Fields:
        - issue_date (may need correction for antedated docs)
        - expiry_date (critical: affects compliance status)
        - certificate_file (can replace with new scan/PDF)
        - notes (update renewal plan)

    Non-Editable:
        - cert_type: Cannot be changed (unique constraint)
        - uploaded_by: Stays as original uploader
        - uploaded_at: Preserved (creation date)
        - yellow_alert_sent: Preserved (alerts history)

    Success Flow:
        1. Admin navigates to edit certificate
        2. Form displays current values
        3. Admin updates expiry_date or other fields
        4. Submits POST
        5. Form validated
        6. Certificate updated
        7. Message: "Certificate updated successfully."
        8. Redirect to document_list
        9. Audit log created (who changed what, when)

    Compliance Impact:
        If expiry_date is changed to a past date:
        - status property now returns 'red'
        - is_compliant() immediately returns False
        - All new expenses/grants are blocked
        - Existing records remain intact (soft delete semantics)

    Notes:
        - updated_at field is automatically refreshed (auto_now=True)
        - Audit trail shows what fields changed via AuditLog
        - File updates create new file in media/compliance/ directory
    """
    doc = get_object_or_404(ComplianceDocument, pk=pk)
    form = ComplianceDocumentForm(request.POST or None, request.FILES or None, instance=doc)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Certificate updated successfully.")
        return redirect("compliance:document_list")
    return render(request, "compliance/document_form.html", {"form": form, "title": "Edit Certificate", "object": doc})


@login_required
@role_required("admin")
def document_detail(request, pk):
    """
    Display detailed view of a single compliance certificate.

    Admin-only view showing all details of a certificate including issue date,
    expiry date, status, days until expiry, upload history, and renewal notes.

    Request Method:
        GET only

    Path Parameters:
        pk (int): Primary key of ComplianceDocument to display

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Response:
        - 200 HTML detail page
        - 404 If certificate with given pk doesn't exist

    Template Used:
        compliance/document_detail.html

    Context Variables:
        doc: The ComplianceDocument instance

    Displayed Information:
        - Certificate type and full name (FCRA Certificate, etc.)
        - Issue date (formatted)
        - Expiry date (formatted)
        - Days until expiry (computed)
        - Current status badge (green/yellow/red)
        - Status label (Valid / Expiring Soon / Expired)
        - Uploaded by (admin name who uploaded)
        - Uploaded at (timestamp)
        - Last updated (timestamp)
        - Notes field content
        - Link to certificate file (download)
        - Alert email history (when yellow alert was sent)

    Links/Actions Available:
        - Edit certificate (button to document_edit view)
        - Back to list (navigate to document_list)
        - Download certificate file

    Use Cases:
        - Quick reference during audit
        - Verify certificate details before renewal
        - Check when renewal is due
        - See when yellow alerts were sent
        - Access certificate file for external verification

    Notes:
        - Status and days_to_expiry are computed live (not cached)
        - Soft deletion not applicable (certs never deleted)
        - Audit logs show history of all changes (via AuditLog)
    """
    doc = get_object_or_404(ComplianceDocument, pk=pk)
    return render(request, "compliance/document_detail.html", {"doc": doc})
