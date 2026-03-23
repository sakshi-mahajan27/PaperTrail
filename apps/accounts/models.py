from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser with role-based access control.

    This model implements the foundation of PaperTrail's role-based access control (RBAC)
    system. Each user has one of three roles: Admin, Finance Manager, or Auditor. Roles
    determine what operations (views, creates, deletes) a user can perform across the
    application.

    Role Definitions:
    - **Admin**: Full system access. Can manage users, certificates, and system settings.
    - **Finance Manager**: Can create/edit expenses, grants, and donor records.
    - **Auditor**: Read-only access to all data. Can view audit logs and generate reports.

    Fields:
        username (str): Inherited from AbstractUser. Unique identifier.
        first_name (str): Inherited from AbstractUser.
        last_name (str): Inherited from AbstractUser.
        email (str): Inherited from AbstractUser.
        password (str): Inherited from AbstractUser. Hashed with pbkdf2_sha256.
        role (str): One of 'admin', 'finance', 'auditor'. Defaults to 'auditor'.
        phone (str): Optional contact phone number. Max 20 characters.
        is_active (bool): Inherited from AbstractUser. Enables/disables user login.
        date_joined (datetime): Inherited from AbstractUser.

    Examples:
        # Create an admin user
        user = User.objects.create_user(
            username='john_admin',
            email='john@ngo.org',
            password='securepass123',
            first_name='John',
            last_name='Doe',
            role=User.ROLE_ADMIN,
            phone='9876543210'
        )

        # Check user's role
        if user.is_finance:
            # User is Finance Manager
            pass
    """

    ROLE_ADMIN = "admin"
    ROLE_FINANCE = "finance"
    ROLE_AUDITOR = "auditor"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_FINANCE, "Finance Manager"),
        (ROLE_AUDITOR, "Auditor"),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_AUDITOR,
    )
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        """
        Check if user has Admin role.

        Returns:
            bool: True if user.role == 'admin', False otherwise
        """
        return self.role == self.ROLE_ADMIN

    @property
    def is_finance(self):
        """
        Check if user has Finance Manager role.

        Finance Managers can create and edit financial records like expenses,
        grants, and donors. They also have read access to all data.

        Returns:
            bool: True if user.role == 'finance', False otherwise
        """
        return self.role == self.ROLE_FINANCE

    @property
    def is_auditor(self):
        """
        Check if user has Auditor role.

        Auditors have read-only access to all application data and can
        generate financial reports and view audit logs.

        Returns:
            bool: True if user.role == 'auditor', False otherwise
        """
        return self.role == self.ROLE_AUDITOR

    @property
    def can_write(self):
        """
        Finance Manager can create/edit financial records.

        This permission gate is used to restrict write operations (create/update)
        to Finance Manager role only. Used by @write_required and @finance_required
        decorators.

        Returns:
            bool: True if user role == ROLE_FINANCE, False otherwise

        Used In:
            - @write_required decorator (accounts/decorators.py)
            - expense_create/edit views
            - grant_create/edit views
            - donor_create/edit views
        """
        return self.role == self.ROLE_FINANCE
