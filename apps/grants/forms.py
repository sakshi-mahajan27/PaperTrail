from django import forms
from .models import Grant
from apps.donors.models import Donor


class GrantForm(forms.ModelForm):
    """
    Django form for creating and editing Grant records.

    Accepts grant details: donor, name, budget, date range, purpose, status.
    Includes form-level validation (end_date > start_date) and Bootstrap styling.

    Fields:
        donor (ModelChoiceField → Donor):
            Dropdown to select which donor authorized this grant.
            Queryset filtered to active donors only (is_active=True).
            Required field.

        name (CharField, max_length=250):
            Grant name/title for identification.
            Examples: "Rural Education 2024", "Health Program Q4"
            Required field.

        total_amount (DecimalField):
            Total budget authorized (in ₹) for this grant.
            Widget: NumberInput with step=0.01 for precise currency entry.
            Required field.

        start_date (DateField):
            First date expenses can be charged to this grant.
            Widget: HTML5 date input (type="date") for date picker.
            Required field.

        end_date (DateField):
            Last date expenses can be charged to this grant.
            Widget: HTML5 date input (type="date") for date picker.
            Validated: must be after start_date.

        purpose (TextField):
            Narrative description of what grant money can be used for.
            Widget: Textarea with 3 rows, form-control Bootstrap class.
            Examples: "Fund teacher salaries", "Purchase medical equipment"
            Required field.

        status (ChoiceField):
            Lifecycle status (pending/active/closed).
            Widget: Select dropdown (form-select Bootstrap class).
            Default: PENDING (user can change to ACTIVE when ready).

        agreement_file (FileField, optional):
            Upload original donor agreement document (PDF/Word).
            Optional—many grants don't have formal docs.
            Widget: ClearableFileInput (allows clear existing file on edit).

    Styling:
        All input fields use Bootstrap classes (form-control, form-select).
        Provides consistent UI with rest of PaperTrail.
        Classes applied via widget attrs dictionary.

    Initialization (__init__):
        Filters donor queryset to active donors only:
        ```python
        self.fields["donor"].queryset = Donor.objects.filter(is_active=True)
        ```
        Ensures users can't assign grant to soft-deleted/inactive donors.
        Prevents orphaning grants to donors that are "gone".

    Validation - Form Level (clean):
        Cross-field validation rule:
        - end_date must be strictly after start_date
        - Raises ValidationError if end_date <= start_date
        - Example error: "End date must be after the start date."

        Why this validation?
        - Grant period must be forward-looking (future or currently active)
        - Prevents data entry errors (accidental date swap)
        - Impossible grants (same-day or reversed) caught early

        Not Validated Here (Validated in Views):
        - is_compliant() check: NGO must have all certificates
        - Validated in grant_create view (not form level)
        - This allows editing grants even if compliance broken now

    Use Cases:

        CREATE (grant_create view):
        ```python
        form = GrantForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            form.save()  # Creates new Grant, created_by not set here
        ```
        Note: grant_create calls form.save() without commit=False,
               so new Grant goes straight to DB with status=PENDING.

        EDIT (grant_edit view):
        ```python
        form = GrantForm(request.POST or None, request.FILES or None, instance=grant)
        if form.is_valid():
            form.save()  # Updates existing Grant in place
        ```
        Preserves created_at, updates updated_at auto-timestamp.

    Error Handling:
        Form errors displayed in template:
        - Field errors below each input
        - Non-field errors at top (e.g., end_date validation)
        - User sees friendly messages

    Related Models:
        - Donor: ForeignKey relationship
          Currently active donors included in dropdown.
        - Grant: target of ModelForm
        - ExpenseAllocation: Not directly in form
          (allocations edited separately in expense forms)

    Notes:
        - No file path validation (Django handles file storage)
        - No uniqueness check on grant name
          (multiple grants can have same name—use (donor, name) for uniqueness)
        - Agreement file optional—many grants lack formal docs
    """
    class Meta:
        model = Grant
        fields = ["donor", "name", "total_amount", "start_date", "end_date", "purpose", "status", "agreement_file"]
        widgets = {
            "donor": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "purpose": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "agreement_file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active donors in the dropdown (soft-delete support)
        self.fields["donor"].queryset = Donor.objects.filter(is_active=True)

    def clean(self):
        """
        Cross-field validation: end_date must be after start_date.

        Checks that the grant period is logically ordered (not backwards).

        Raises:
            ValidationError: If end_date <= start_date with message
                            "End date must be after the start date."

        Why Cross-Field?
            Individual field validation (CharField, DateField) can't compare
            multiple fields. clean() is called after all field validations
            pass, allowing us to check relationships between fields.

        Implementation Steps:
            1. Call super().clean() to run field-level validation first
            2. Get cleaned_data (validated values from form)
            3. Extract start and end dates
            4. Check if both exist and end <= start
            5. If invalid, raise ValidationError (displayed in template)

        Error Message:
            "End date must be after the start date."
            Added to non_field_errors (displayed at top of form).

        Examples:
            - start=2024-01-01, end=2024-12-31: Valid ✓
            - start=2024-01-01, end=2024-01-01: Invalid (same day) ✗
            - start=2024-12-31, end=2024-01-01: Invalid (reversed) ✗
            - start=None, end=2024-12-31: Skipped (start not filled)

        Related:
            Form-level validation complements model-level validation.
            If same validation needed in multiple places, consider model validators.
        """
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end <= start:
            raise forms.ValidationError("End date must be after the start date.")
        return cleaned
