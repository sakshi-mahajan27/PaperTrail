from django.db import models
from apps.donors.models import Donor


class Grant(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="grants")
    name = models.CharField(max_length=250)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    purpose = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    agreement_file = models.FileField(upload_to="grants/agreements/", blank=True, null=True)
    is_active = models.BooleanField(default=True)  # soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.donor.name})"

    @property
    def utilized_amount(self):
        from django.db.models import Sum
        result = self.allocations.filter(expense__is_active=True).aggregate(total=Sum("allocated_amount"))
        return result["total"] or 0

    @property
    def remaining_amount(self):
        return self.total_amount - self.utilized_amount

    @property
    def burn_rate(self):
        if self.total_amount == 0:
            return 0
        return round((self.utilized_amount / self.total_amount) * 100, 1)
