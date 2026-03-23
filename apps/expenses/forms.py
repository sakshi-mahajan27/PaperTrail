from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import Expense, ExpenseAllocation
from apps.grants.models import Grant
from apps.compliance.utils import is_compliant, get_compliance_issues


class ExpenseForm(forms.ModelForm):
    """
    Form for creating and editing expense records.

    This form handles the main expense fields (title, amount, date, description, receipt).
    It includes a critical compliance gate check: expenses can only be created if all
    NGO compliance certificates are valid (is_compliant() returns True).

    Fields:
        title (str): Brief expense description. Required.
        total_amount (decimal): Amount spent. Required.
        expense_date (date): When expense occurred. Required.
            Later validated against grant period in _validate_allocations()
        description (str):  Extra notes. Optional.
        receipt (file): Invoice/receipt. Required.

    Validation Layers:
        1. clean_receipt() → File must exist
        2. clean() → is_compliant() check (compliance gate)
        3. View _validate_allocations() → Allocations must sum and fit grants

    Styling:
        Bootstrap CSS classes (form-control, form-select) for UI consistency

    Compliance Gate (Critical):
        If is_compliant() returns False (any cert expired or missing):
        - ValidationError raised in clean()
        - Error lists all issues via get_compliance_issues()
        - User sees: "Compliance gate failed: FCRA is missing. | 80G is expired."
        - Prevents creation/editing of expenses when NGO not in good standing

    Used By:
        - expense_create view: New expense
        - expense_edit view: Update expense

    Example Success:
        form = ExpenseForm({
            'title': 'Staff Salaries',
            'total_amount': '50000.00',
            'expense_date': '2025-03-20',
            'receipt': <file>
        })
        if form.is_valid():  # Calls clean() -> is_compliant() check
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()

    Example Failure (Compliance):
        # FCRA certificate expired
        form = ExpenseForm(data)
        if not form.is_valid():
            # Error: "Compliance gate failed: FCRA Certificate has expired."
    """
    class Meta:
        model = Expense
        fields = ["title", "total_amount", "expense_date", "description", "receipt"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "id": "id_total_amount"}),
            "expense_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "receipt": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def clean_receipt(self):
        """
        Validate that a receipt file is provided.

        On create: receipt must be provided
        On edit: if no new receipt uploaded, existing file is preserved

        Returns:
            file: The receipt file

        Raises:
            ValidationError: If receipt is empty/missing
        """
        receipt = self.cleaned_data.get("receipt")
        # On create, receipt is required. On update, if no new file, the existing field value is preserved.
        if not receipt:
            raise ValidationError("A receipt file is required for every expense.")
        return receipt

    def clean(self):
        """
        Validate that NGO is in compliance (all certificates valid).

        This is the PRIMARY COMPLIANCE GATE for expense creation/editing.
        It ensures expenses are only recorded when the NGO meets all regulatory
        requirements (has all 3 certificates and none are expired).

        Business Logic:
            Call is_compliant() which returns:
            - True: All 3 certs exist and none are 'red' (expired)
            - False: At least one cert missing or expired

        On Failure:
            - Calls get_compliance_issues() to list problems
            - Raises ValidationError with human-readable issue list
            - Examples:
                "Compliance gate failed: FCRA is missing."
                "Compliance gate failed: 80G Certificate has expired."

        Used For:
            - expense_create: Blocks new expenses if not compliant
            - expense_edit: Blocks editing if not compliant (stricter than view)

        Note:
            is_compliant() permits 'yellow' status (expiring soon ≤180 days)
            Only 'red' (expired) blocks operations

        See Also:
            - is_compliant() in apps/compliance/utils.py
            - get_compliance_issues() returns list of issue strings
        """
        cleaned = super().clean()
        if not is_compliant():
            issues = get_compliance_issues()
            raise ValidationError("Compliance gate failed: " + " | ".join(issues))
        return cleaned


class ExpenseAllocationForm(forms.ModelForm):
    """
    Form for allocating expense amounts to specific grants.

    Part of the AllocationFormSet, this form is repeated for each allocation
    row in the create/edit expense workflow. User selects grant and amount
    to allocate from the expense to that specific grant's budget.

    Fields:
        grant (choice): Select which grant pays for this portion. Required.
        allocated_amount (decimal): How much of the expense goes to this grant. Required.

    Grant Filtering:
        Only active grants with status='active' shown (filtering enforced
        in __init__). This prevents allocating to inactive/closed grants.

    Styling:
        Bootstrap CSS (form-control, form-select) with special IDs:
        - CSS class "allocation-grant" on grant dropdown (JS targeting)
        - CSS class "allocation-amount" on amount field (for price sum validation)

    Used By:
        AllocationFormSet (declared below)

    Example (in formset context):
        form0 = AllocationForm({
            'grant': 42,
            'allocated_amount': '3000.00'
        })
        form0.is_valid()  # Only valid if grant 42 exists and is active

    JavaScript Integration:
        Template likely uses allocation-grant and allocation-amount classes
        to compute running total of allocations (should equal expense total)
    """
    class Meta:
        model = ExpenseAllocation
        fields = ["grant", "allocated_amount"]
        widgets = {
            "grant": forms.Select(attrs={"class": "form-select allocation-grant"}),
            "allocated_amount": forms.NumberInput(attrs={"class": "form-control allocation-amount", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter grants to only active, non-closed ones
        # Prevents user from accidentally allocating to a closed grant
        self.fields["grant"].queryset = Grant.objects.filter(is_active=True, status="active")


# AllocationFormSet: Collection of expense allocation forms
# min_num=1, validate_min=True → At least 1 allocation required
# extra=1 → One blank form rows for adding new allocations
# can_delete=True → Check box to remove allocation row
AllocationFormSet = inlineformset_factory(
    Expense,
    ExpenseAllocation,
    form=ExpenseAllocationForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
