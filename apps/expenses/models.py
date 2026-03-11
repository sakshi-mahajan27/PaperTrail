from django.db import models
from apps.accounts.models import User
from apps.grants.models import Grant


class Expense(models.Model):
    title = models.CharField(max_length=300)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date = models.DateField()
    description = models.TextField(blank=True)
    receipt = models.FileField(upload_to="expenses/receipts/")  # required – enforced at form level
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="expenses")
    is_active = models.BooleanField(default=True)  # soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.title} – ₹{self.total_amount} ({self.expense_date})"


class ExpenseAllocation(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="allocations")
    grant = models.ForeignKey(Grant, on_delete=models.PROTECT, related_name="allocations")
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        unique_together = [("expense", "grant")]

    def __str__(self):
        return f"{self.expense.title} → {self.grant.name}: ₹{self.allocated_amount}"
