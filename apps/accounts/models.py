from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model with role-based access."""

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
        return self.role == self.ROLE_ADMIN

    @property
    def is_finance(self):
        return self.role == self.ROLE_FINANCE

    @property
    def is_auditor(self):
        return self.role == self.ROLE_AUDITOR

    @property
    def can_write(self):
        """Finance Manager and Admin can create/edit records."""
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE)
