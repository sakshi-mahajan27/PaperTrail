from django import forms
from .models import Donor


class DonorForm(forms.ModelForm):
    """
    Form for creating and editing donor records.

    Used by Finance Managers to register new donors and update donor details.
    Includes all donor fields except is_active (handled separately in views).

    Fields:
        name (str): Donor name. Required.
        donor_type (choice): Individual/Organization/Government/Corporate
        email (str): Email address. Optional.
        phone (str): Phone number. Optional.
        country (str): Country. Defaults to 'India'.
        address (str): Mailing address. Optional, textarea.
        pan_number (str): Indian PAN. Optional.
        notes (str): Internal notes. Optional, textarea.

    Styling:
        All fields use Bootstrap CSS classes (form-control, form-select)
        for consistent UI.

    Validation:
        - No custom validation (model-level constraints handle most)
        - Required fields: name only
        - Optional fields: email, phone, address, pan_number, notes

    Used By:
        - donor_create view: Register new donor
        - donor_edit view: Update donor details

    Example:
        form = DonorForm({'name': 'ABC Foundation', 'donor_type': 'corporate'})
        if form.is_valid():
            donor = form.save()
    """
    class Meta:
        model = Donor
        fields = ["name", "donor_type", "email", "phone", "country", "address", "pan_number", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "donor_type": forms.Select(attrs={"class": "form-select"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "pan_number": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
