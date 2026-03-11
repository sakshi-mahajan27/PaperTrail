from django import forms
from .models import ComplianceDocument


class ComplianceDocumentForm(forms.ModelForm):
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
        cleaned = super().clean()
        issue = cleaned.get("issue_date")
        expiry = cleaned.get("expiry_date")
        if issue and expiry and expiry <= issue:
            raise forms.ValidationError("Expiry date must be after the issue date.")
        return cleaned
