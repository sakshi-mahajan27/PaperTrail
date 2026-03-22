from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"})
    )


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # Render the boolean `is_active` as a Bootstrap-style checkbox/switch
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(attrs={"class": "form-check-input"})


class UserUpdateForm(UserChangeForm):
    password = None  # hide raw password field

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # Render the boolean `is_active` as a Bootstrap-style checkbox/switch
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(attrs={"class": "form-check-input"})
