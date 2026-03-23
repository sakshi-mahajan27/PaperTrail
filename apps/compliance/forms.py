from django import forms
from .models import ComplianceDocument


class ComplianceDocumentForm(forms.ModelForm):
    """
    Form for uploading and editing compliance certificates.

    Used by admin users to manage the three required NGO compliance documents:
    FCRA, 80G, and 12A certificates. This form validates that certificates
    have sensible dates (issue before expiry).

    Fields:
        cert_type (choice): One of 'FCRA', '80G', or '12A'
            - Required
            - unique=True in model (only one of each type)
            - Shown as dropdown select

        issue_date (date): When the certificate was issued
            - Required
            - HTML5 date input
            - Must be before expiry_date (validated in clean())

        expiry_date (date): When the certificate expires
            - Required
            - HTML5 date input
            - Must be after issue_date (validated in clean())
            - Critical field: used to compute compliance status

        certificate_file (file): The PDF or image of the certificate
            - Required
            - ClearableFileInput (allows seeing current file and clearing)
            - No file size validation (enforced at storage level)

        notes (str): Optional renewal notes or exemption details
            - Optional (blank=True)
            - 3-row textarea
            - Used for internal reminders/documentation

    Styling:
        All fields use Bootstrap CSS classes (form-select, form-control)
        for consistent UI across the application.

    Validation:
        - clean() method ensures expiry_date > issue_date
        - Raises ValidationError if dates are out of order
        - Model-level unique constraint on cert_type (only one per type)

    Used By:
        - certificate_upload view: Create new certificate
        - certificate_edit view: Update existing certificate

    Example:
        # Create FCRA certificate
        form = ComplianceDocumentForm({
            'cert_type': 'FCRA',
            'issue_date': '2023-03-01',
            'expiry_date': '2028-03-01',
            'notes': 'Renewal scheduled for Feb 2028',
            'certificate_file': <file object>
        })
        if form.is_valid():
            doc = form.save(commit=False)
            doc.uploaded_by = request.user  # Track who uploaded
            doc.save()

    Notes:
        - All three certificates are required for system to be 'compliant'
        - Expiry date directly controls compliance gating for expenses/grants
        - see is_compliant() in utils.py for how these are checked
    """
    class Meta:
        model = ComplianceDocument
        fields = ["cert_type", "issue_date", "expiry_date", "certificate_file", "notes"]
        widgets = {
            "cert_type": forms.Select(attrs={"class": "form-select"}),
            "issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "certificate_file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        """
        Validate that issue_date is before expiry_date.

        This cross-field validation ensures dates make logical sense:
        a certificate can't expire before it was issued.

        Raises:
            ValidationError: If expiry_date <= issue_date

        Called:
            - Automatically by form.is_valid()
            - After individual field validation (clean_<field>())
        """
        cleaned = super().clean()
        issue = cleaned.get("issue_date")
        expiry = cleaned.get("expiry_date")
        if issue and expiry and expiry <= issue:
            raise forms.ValidationError("Expiry date must be after the issue date.")
        return cleaned
