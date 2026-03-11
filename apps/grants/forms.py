from django import forms
from .models import Grant
from apps.donors.models import Donor


class GrantForm(forms.ModelForm):
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
        self.fields["donor"].queryset = Donor.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end <= start:
            raise forms.ValidationError("End date must be after the start date.")
        return cleaned
