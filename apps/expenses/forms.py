from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import Expense, ExpenseAllocation
from apps.grants.models import Grant
from apps.compliance.utils import is_compliant, get_compliance_issues


class ExpenseForm(forms.ModelForm):
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
        receipt = self.cleaned_data.get("receipt")
        # On create, receipt is required. On update, if no new file, the existing field value is preserved.
        if not receipt:
            raise ValidationError("A receipt file is required for every expense.")
        return receipt

    def clean(self):
        cleaned = super().clean()
        if not is_compliant():
            issues = get_compliance_issues()
            raise ValidationError("Compliance gate failed: " + " | ".join(issues))
        return cleaned


class ExpenseAllocationForm(forms.ModelForm):
    class Meta:
        model = ExpenseAllocation
        fields = ["grant", "allocated_amount"]
        widgets = {
            "grant": forms.Select(attrs={"class": "form-select allocation-grant"}),
            "allocated_amount": forms.NumberInput(attrs={"class": "form-control allocation-amount", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grant"].queryset = Grant.objects.filter(is_active=True, status="active")


AllocationFormSet = inlineformset_factory(
    Expense,
    ExpenseAllocation,
    form=ExpenseAllocationForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
