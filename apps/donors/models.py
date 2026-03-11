from django.db import models


class Donor(models.Model):
    TYPE_INDIVIDUAL = "individual"
    TYPE_ORGANIZATION = "organization"
    TYPE_GOVERNMENT = "government"
    TYPE_CORPORATE = "corporate"

    TYPE_CHOICES = [
        (TYPE_INDIVIDUAL, "Individual"),
        (TYPE_ORGANIZATION, "Organization"),
        (TYPE_GOVERNMENT, "Government"),
        (TYPE_CORPORATE, "Corporate"),
    ]

    name = models.CharField(max_length=200)
    donor_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_INDIVIDUAL)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="India")
    address = models.TextField(blank=True)
    pan_number = models.CharField(max_length=20, blank=True, verbose_name="PAN Number")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)  # soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_donor_type_display()})"
