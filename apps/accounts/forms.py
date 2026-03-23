from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import User


class LoginForm(AuthenticationForm):
    """
    Enhanced login form with Bootstrap styling.

    This form extends Django's default AuthenticationForm with custom widgets
    that integrate Bootstrap CSS classes for consistent UI styling across
    the application.

    Fields:
        username (str): User account username
        password (str): User account password

    Inherits from:
        django.contrib.auth.forms.AuthenticationForm

    Features:
        - Bootstrap form-control class applied to all fields
        - Placeholder text for user guidance
        - Password field masked (type="password")

    Usage:
        In views.py: form = LoginForm(request, data=request.POST or None)
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"})
    )


class UserCreateForm(UserCreationForm):
    """
    Form for creating new users with role assignment.

    Admin users use this form to register new accounts in the system.
    It extends Django's UserCreationForm to include PaperTrail-specific
    fields like role and phone number.

    Fields:
        username (str): Unique identifier, required
        first_name (str): User's first name, optional
        last_name (str): User's last name, optional
        email (str): User's email address, optional
        phone (str): User's phone number, optional (PaperTrail custom)
        role (str): One of 'admin', 'finance', 'auditor' (PaperTrail custom)
        password1 (str): Password, required
        password2 (str): Password confirmation, required

    Validation:
        - password1 and password2 must match (from UserCreationForm)
        - username must be unique
        - All text fields have Bootstrap styling applied

    Used By:
        /accounts/user/new (admin only)
    """
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap styling to all form fields
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # Render the boolean `is_active` as a Bootstrap-style checkbox/switch
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(attrs={"class": "form-check-input"})


class UserUpdateForm(UserChangeForm):
    """
    Form for editing existing user accounts.

    Admin users use this form to modify user details, roles, and access.
    The password field is hidden (set to None) to prevent accidental
    password changes. Use Django's change password view instead.

    Fields:
        username (str): User's username, required (unique)
        first_name (str): User's first name, optional
        last_name (str): User's last name, optional
        email (str): User's email address, optional
        phone (str): User's phone number, optional
        role (str): One of 'admin', 'finance', 'auditor' (can be changed)
        is_active (bool): Enable/disable user login

    Validation:
        - username must remain unique
        - All text fields have Bootstrap styling applied
        - password field is hidden for security

    Used By:
        /accounts/user/<id>/edit (admin only)

    Notes:
        - Password changes should be done via separate change-password view
        - is_active checkbox controls whether user can log in
    """
    password = None  # hide raw password field

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap styling to all form fields
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # Render the boolean `is_active` as a Bootstrap-style checkbox/switch
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(attrs={"class": "form-check-input"})
