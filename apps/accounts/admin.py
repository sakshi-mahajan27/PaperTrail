from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Django admin interface for the custom User model.

    This admin class extends Django's built-in UserAdmin to include
    PaperTrail-specific fields like role and phone number. It provides
    a comprehensive interface for user management.

    Display & Filtering:
        list_display: Shows username, email, role, is_active status, and
                     join date in the admin list view
        list_filter: Allows filtering users by role and active status

    Fields:
        fieldsets: Organizes fields into two sections:
            1. Default (username, password, email, etc.) from UserAdmin
            2. PaperTrail section (role, phone) for NGO-specific fields
        add_fieldsets: Custom fields when creating a new user

    Features:
        - Role assignment ('admin', 'finance', 'auditor')
        - Phone number storage
        - Active/inactive toggles for quick access control
        - Full integration with Django's user management

    Example Usage:
        - Change user's role from 'auditor' to 'finance'
        - Deactivate a user by unchecking is_active
        - View user creation date (date_joined)
    """
    list_display = ["username", "email", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active"]
    fieldsets = UserAdmin.fieldsets + (
        ("PaperTrail", {"fields": ("role", "phone")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("PaperTrail", {"fields": ("role", "phone")}),
    )
