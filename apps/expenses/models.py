from django.db import models
from apps.accounts.models import User
from apps.grants.models import Grant


class Expense(models.Model):
    """
    Record of funds spent by the NGO.

    This model tracks individual expense entries (e.g., staff salaries, office rent,
    program delivery costs). Each expense must be allocated to one or more grants
    to track which funding source(s) paid for it.

    Business Purpose:
        - Document all fund utilization (required for audits)
        - Track expenses against grant budgets
        - Enable allocation of shared expenses across multiple grants
        - Provide receipt/invoice documentation

    Compliance Gates:
        Before creating/editing expenses, the system checks:
        - is_compliant() must return True (all 3 certificates valid)
        - If any certificate is expired (red), expenses are blocked
        - Yellow (expiring soon) still allows expenses with warning

    Soft Deletion:
        Expenses use is_active flag (soft delete) instead of true deletion.
        deleted expenses still link to historical allocations but are filtered out.

    Fields:
        title (str): Brief description of the expense.
            Max 300 chars, e.g., "Staff Salaries - March"

        total_amount (decimal): Total amount spent.
            14 digits total, 2 decimal places (supports ₹999,999,999,999.99)
            Stored as DecimalField (not Float) for accuracy with money

        expense_date (date): When the expense occurred.
            Critical for checking if it falls within grant period (start_date to end_date)
            Used by _validate_allocations() in views.py

        description (str): Detailed notes about the expense.
            Optional, free text
            For internal documentation and audit trail

        receipt (FileField): Uploaded invoice or receipt.
            Required (enforced at form level)
            Stored in media/expenses/receipts/ directory
            Supports PDF, images, etc.

        created_by (ForeignKey): User who recorded the expense.
            Links to User model with PROTECT (can't delete user if expense exists)
            For accountability: who entered this data

        is_active (bool): Soft-delete flag.
            Default=True (active)
            False = soft-deleted (preserved for history)
            Filtered in views using is_active=True

        created_at (datetime): When the expense was logged.
            auto_now_add, never changes after creation

        updated_at (datetime): When the expense was last modified.
            auto_now, updated on every save

    Relationships:
        - ForeignKey to User (created_by): One user can create many expenses
        - Reverse FK from ExpenseAllocation: One expense can have many allocations
            Access via expense.allocations.all()

    Metadata:
        ordering: ["-expense_date", "-created_at"]
            Most recent expenses first (by date, then creation)

    Query Examples:
        # Get all active expenses
        active = Expense.objects.filter(is_active=True)

        # Get expenses from a specific month
        from django.utils import timezone
        from datetime import date, timedelta
        start = date(2025, 3, 1)
        end = date(2025, 3, 31)
        march = Expense.objects.filter(
            is_active=True,
            expense_date__gte=start,
            expense_date__lte=end
        )

        # Get expenses created by finance manager john
        john_expenses = Expense.objects.filter(is_active=True, created_by__username='john')

        # Get total spending
        from django.db.models import Sum
        total = Expense.objects.filter(is_active=True).aggregate(
            total=Sum('total_amount')
        )['total'] or 0

    Validation Flow:
        1. ExpenseForm.clean_receipt() → Requires receipt file
        2. ExpenseForm.clean() → is_compliant() check (blocks if red cert)
        3. View: _validate_allocations() → Cross-allocation checks:
           - expense_date within grant period
           - allocations sum equals total_amount
           - grant budget not exceeded
        4. transaction.atomic() → All-or-nothing save

    Performance Cons iderations:
        - ordering by date/time: May need index for large datasets
        - select_related("created_by"): Used to fetch user in list views
        - prefetch_related("allocations__grant") for showing all allocations
        - No pagination currently (could hit performance with 1M+ records)

    Security Notes:
        - Receipt file stored on disk (S3/GCS recommended for production)
        - File type not validated (admin responsibility)
        - created_by set server-side (can't be spoofed by user)
        - Soft delete preserves data for audits

    Example Lifecycle:
        1. Finance team spends ₹5,000 on office rent (shared across 2 grants)
        2. Manager creates Expense: title="March Office Rent", total_amount=5000
        3. Uploads rent receipt PDF
        4. System prompts: "Allocate ₹5,000 to grants"
        5. Allocates: ₹3,000 to "Training Grant", ₹2,000 to "Food Security Grant"
        6. Expense saved, allocations linked
        7. Both grants' remaining_amount updated (burns their budgets)
        8. Audit log created (action=created, who created when)
    """

    title = models.CharField(
        max_length=300,
        help_text="Brief description of the expense"
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total amount spent (e.g., 5000.00)"
    )
    expense_date = models.DateField(
        help_text="Date when the expense occurred (must be within grant period)"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional detailed notes for audit trail"
    )
    receipt = models.FileField(
        upload_to="expenses/receipts/",
        help_text="Invoice or receipt. Required and enforced at form level."
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="expenses",
        help_text="User who recorded this expense"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag. False = deactivated but data preserved."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When expense was logged (never changes)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When expense was last modified"
    )

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.title} – ₹{self.total_amount} ({self.expense_date})"


class ExpenseAllocation(models.Model):
    """
    Links an expense to a grant with a specific amount.

    This is a through table (many-to-many with extra field) that maps expenses
    to grants. One expense can be split across multiple grants, and the allocated
    amounts track budget utilization per grant.

    Business Purpose:
        - Support allocation of shared expenses across multiple funding sources
        - Track which grant budget is used for each expense
        - Enable grant budget validation (_validate_allocations in views)
        - Support flexible expense categorization

    Example Scenario:
        Expense: ₹10,000 office rent (shared between 3 programs)
        Allocations:
        - Grant "Child Health": ₹4,000
        - Grant "Education": ₹3,500
        - Grant "Corporate Social Responsibility": ₹2,500
        = ₹10,000 total

    Fields:
        expense (ForeignKey): The expense being allocated.
            Links to Expense model with CASCADE on delete
            If expense deleted, allocation deleted too

        grant (ForeignKey): The grant funding this portion.
            Links to Grant model with PROTECT on delete
            Cannot delete grant if allocations exist (prevents orphaning)

        allocated_amount (decimal): Amount charged to this grant.
            14 digits, 2 decimal places (same as Expense.total_amount)
            Can be full or partial expense amount

    Constraints:
        unique_together: [("expense", "grant")]
            Prevents duplicate allocation of same expense to same grant
            If need to change amount, edit existing allocation

    Metadata:
        No explicit ordering (depends on parent Expense or Grant)

    Validation (View-Level):
        _validate_allocations() in expenses/views.py checks:
        1. Sum of allocations == Expense.total_amount (no over/under)
        2. Expense_date within grant's start_date to end_date
        3. allocated_amount doesn't exceed grant's remaining budget
        4. expense.is_active=True (can't allocate deleted expenses)

    Query Examples:
        # Get all allocations for a grant
        grant = Grant.objects.get(name='Training')
        allocations = grant.allocations.filter(expense__is_active=True)

        # Get total allocated to a grant
        from django.db.models import Sum
        total = grant.allocations.filter(expense__is_active=True).aggregate(
            total=Sum('allocated_amount')
        )['total'] or 0

        # Find grant's remaining budget
        remaining = grant.total_amount - total

        # Get all expenses allocated to a grant
        expenses = [a.expense for a in grant.allocations.filter(expense__is_active=True)]

    Performance:
        - unique_together enforced by database
        - No explicit indexing (small dataset relative to grants/expenses)
        - select_related("expense", "grant") useful in views
        - Can be high volume if expense split across many grants

    Example Lifecycle:
        1. Expense "Office Rent" (₹10,000) created
        2. AllocationForm presented with grant selector
        3. Admin allocates ₹3,000 to "Training" → ExpenseAllocation created
        4. Admin allocates ₹4,000 to "Food Security" → Another created
        5. Admin allocates ₹3,000 to "Advocacy" → Third created
        6. Form validation: 3,000 + 4,000 + 3,000 = 10,000 ✓
        7. View saves: expense.save(), formset.save() (all in transaction)
        8. Expense visible in expense_list, allocations visible in grant detail
        9. Audit logs created for both Expense and ExpenseAllocation

    Soft Deletion Notes:
        If Expense is soft-deleted (is_active=False):
        - Allocation remains in database
        - expense__is_active=True filters exclude it from views
        - Grant.utilized_amount includes only active expenses
        - Budget reporting accurate (only active expenses used)
    """

    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="allocations",
        help_text="The expense being allocated"
    )
    grant = models.ForeignKey(
        Grant,
        on_delete=models.PROTECT,
        related_name="allocations",
        help_text="The grant funding this allocation"
    )
    allocated_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Amount from this expense charged to this grant"
    )

    class Meta:
        unique_together = [("expense", "grant")]

    def __str__(self):
        return f"{self.expense.title} → {self.grant.name}: ₹{self.allocated_amount}"
