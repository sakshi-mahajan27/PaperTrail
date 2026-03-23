from django.db import models
from apps.donors.models import Donor


class Grant(models.Model):
    """
    Fundraising agreement linking a donor and a budget for a specific purpose.

    A Grant represents money a donor has authorized for the NGO to spend on a
    specific project or program within a specific time period. Grants are the
    main vehicle for budget allocation—expenses are allocated to grants,
    which track progress against the donor's authorization.

    Business Purpose:
        Donors contribute funds with RESTRICTIONS (can only use money for
        specific purpose, within specific dates). Grants formalize these
        restrictions and enforce budget discipline.

        Example: Donor gives ₹10,00,000 for "Rural Education Program"
        from Jan 2024 to Dec 2024. This is ONE GRANT.

    Fields:
        donor (ForeignKey → Donor):
            The donor who authorized this funding.
            on_delete=PROTECT prevents accidental orphaning (if donor is
            "deleted" via is_active=False, grants preserved for history).
            Examples: ABC Foundation, Individual Donor, Government Ministry

        name (CharField, max_length=250):
            Grant name/title for identification.
            Examples: "Rural Education 2024", "Health Program Q4", "Emergency Relief"

        total_amount (DecimalField, max_digits=14, decimal_places=2):
            Total budget authorized by donor for this grant (in ₹).
            Will be spent via ExpenseAllocation records.
            Stored as Decimal for precision (no floating-point errors).
            Examples: 10000.00, 500000.50, 1000000.00

        start_date (DateField):
            First date when expenses can be charged to this grant.
            Enforced in _validate_allocations: expense_date >= start_date

        end_date (DateField):
            Last date when expenses can be charged to this grant.
            Enforced in _validate_allocations: expense_date <= end_date
            Typically one year from start_date.

        purpose (TextField):
            Narrative description of what grant money can be used for.
            Examples: "Fund teacher salaries at rural schools",
                     "Purchase medical equipment for clinic"
            Used for compliance & audit trail.

        status (CharField, choices=STATUS_CHOICES):
            Lifecycle status of the grant (pending/active/closed).
            - PENDING: Freshly created, not yet active
            - ACTIVE: Expenses can be allocated to this grant
            - CLOSED: Expired or fully utilized, no new allocations
            Used in grant_list view to filter display.

        agreement_file (FileField, blank=True, null=True):
            Original donor agreement document (PDF/Word).
            Uploaded to media/grants/agreements/ directory.
            Optional (many grants don't have formal agreements).
            Linked for audits and external compliance.

        is_active (BooleanField, default=True):
            Soft-delete flag (never actually delete grants).
            If a grant is mistaken or ends early, set is_active=False.
            All views filter is_active=True.
            Preserves historical audit logs and budget calculations.

        created_at (DateTimeField, auto_now_add=True):
            Timestamp when grant was first recorded (immutable).

        updated_at (DateTimeField, auto_now=True):
            Timestamp of last modification (auto-updated on save).
            Shows when grant details (status, dates) were last changed.

    Related Models:
        grant.allocations (Reverse FK from ExpenseAllocation):
            All allocations (expenses) charged to this grant.
            Used for budget calculations:
            - utilized_amount = sum of all allocation amounts
            - remaining_amount = total_amount - utilized_amount
            - burn_rate = (utilized_amount / total_amount) * 100%

    Properties (Calculated Fields):

        utilized_amount (Decimal):
            Total amount of grant already spent.
            Query: Sum of allocated_amount from active ExpenseAllocation records.
            Used for: Budget tracking, remaining budget calculation, burn rate.
            Performance: O(database query), cached per request scope.
            Example: If grant total is ₹10,000 and expenses total ₹6,000 spent,
                     utilized_amount = ₹6,000

        remaining_amount (Decimal):
            Budget still available to spend.
            Calculated: total_amount - utilized_amount
            Used for: Display in templates, validation in _validate_allocations.
            Example: ₹10,000 total - ₹6,000 spent = ₹4,000 remaining
            When this reaches 0, grant is "fully utilized" (no more expenses allowed).

        burn_rate (float):
            Percentage of budget consumed so far.
            Calculated: (utilized_amount / total_amount) * 100, rounded to 1 decimal.
            Edge case: If total_amount = 0, returns 0 (prevents division by zero).
            Used for: Progress visualization, spending analytics.
            Example: ₹6,000 / ₹10,000 = 60.0% burn rate

    Query Patterns:

        All active grants:
        ```python
        Grant.objects.filter(is_active=True).select_related("donor")
        ```
        select_related("donor") avoids N+1: fetches donor in same query.

        Grants by donor:
        ```python
        donor.grants.filter(is_active=True)
        ```
        Uses reverse FK from Donor model.

        Grants by status:
        ```python
        Grant.objects.filter(status=Grant.STATUS_ACTIVE, is_active=True)
        ```
        Used in grant_list view to filter by status_filter parameter.

        Budget summary per grant:
        ```python
        for grant in grants:
            print(f"{grant.name}: {grant.burn_rate}% utilized")
        ```
        This will trigger N additional queries (one per grant for allocations).
        Optimize with prefetch_related if displaying multiple grants' burn rates:
        ```python
        grants.prefetch_related("allocations")
        ```

    Validation:

        Form Level (GrantForm.clean()):
            - end_date must be after start_date
            - Raises ValidationError if end_date <= start_date

        View Level (grant_create view):
            - is_compliant() check: NGO must have all certificates before granting
            - Blocks grant creation if FCRA, 80G, or 12A certificate missing/expired
            - Shows compliance issues to user

        Data Integrity:
            - on_delete=PROTECT: Can't delete donor if grants exist
            - status defaults to PENDING (must manually activate)
            - is_active defaults to True (can soft-delete later)

    Soft-Deletion Semantics:

        If a grant is mistaken, set is_active=False instead of deleting:
        - Preserves all allocations and audit history
        - Preserves expense calculations (burn_rate is based on this grant)
        - Allows "recovery" if mistake is caught later

        Why not hard delete?
        - Breaks expense allocations (orphaned FK references)
        - Loses audit trail (who spent what on which grant)
        - Breaks budget reports (historical spending disappears)

    Relationships With Other Models:

        Donor → Grant:
            One donor can have many grants (multiple programs/years).
            Enforced by ForeignKey(Donor, ..., related_name="grants")

        Grant → Expense:
            One grant can have many expense allocations.
            Indirect: Expense → ExpenseAllocation → Grant
            Example: Single office expense (rent) allocated to 3 grants proportionally.

        Grant → Compliance:
            Grant creation checks is_compliant() for certs.
            But grant status NOT affected by certificate expiry.
            (You can edit a grant even if compliance broken now.)

    Lifecycle Example:

        1. CREATION (pending)
           Finance Manager inputs grant details, submits GrantForm
           Status auto-set to PENDING
           No expenses allowed yet

        2. ACTIVATION
           Donor agrees, manager sets status=ACTIVE
           Now expenses can be allocated to this grant

        3. SPENDING (active)
           Expenses incurred, allocated proportionally to grants
           utilized_amount increases, remaining_amount decreases
           burn_rate increases from 0% toward 100%

        4. CLOSURE (closed)
           2024 ends, grant period expires
           Manager clicks "Close Grant" button
           Status set to CLOSED
           New expenses cannot be allocated here
           But historical data remains for audits

    Performance Notes:

        list_display with utilized_amount:
            Each row shows burn_rate, triggering query-per-grant.
            Consider using annotate() to fetch in batch query.
            Workaround: limit list_per_page in admin.

        prefetch_related("allocations") heavily recommended:
            If accessing .utilized_amount for multiple grants, prefetch first.
            Reduces N+1 queries to 1 query + N property calls.

        Select_related("donor") for list views to avoid N+1 on ForeignKey.

    Audit Tracking:

        All changes to Grant tracked by signals.py:
        - Field changes: name, total_amount, start_date, end_date, status, is_active
        - Captured in AuditLog with before/after values
        - Example log: "status: pending → active" by Finance Manager at timestamp

    Regulatory Notes (NGO Context):

        - Grant record is legal evidence of donor intention
        - Expense allocation to grant proves spending was authorized
        - Audit log shows grant was not modified inappropriately
        - All three together satisfy NGO compliance audits (80G, 12A, FCRA)

    status (choices):
        - PENDING ("pending"): Grant freshly created, awaiting activation
        - ACTIVE ("active"): Grant live, accepting expense allocations
        - CLOSED ("closed"): Grant ended, no more allocations accepted
    """
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
        """
        Total amount spent from this grant (sum of all expense allocations).

        Calculated by summing allocated_amount from all active ExpenseAllocation
        records where this grant is the target.

        Query:
            ```python
            self.allocations.filter(expense__is_active=True).aggregate(
                total=Sum("allocated_amount")
            )["total"] or 0
            ```

        Return Value:
            Decimal or int (0 if no allocations).
            Never negative (allocations are always positive).

        Performance:
            O(database query) - one database hit per property access.
            If accessing for multiple grants in a loop, use prefetch_related.

        Used By:
            - remaining_amount: Subtracted from total_amount
            - burn_rate: Divided by total_amount for percentage
            - Templates: Display "₹6,000 / ₹10,000 spent"
            - _validate_allocations: Enforce budget limits

        Examples:
            - Grant with no expenses: utilized_amount = 0
            - Grant with expenses totalling ₹6,000: utilized_amount = 6000.00
            - If expense is soft-deleted (is_active=False): Doesn't count

        Design Note:
            Always queries from ExpenseAllocation, not direct cache.
            This ensures accuracy if an expense is reallocated after viewing.
            Caching would require invalidation on every allocation change.
        """
        from django.db.models import Sum
        result = self.allocations.filter(expense__is_active=True).aggregate(total=Sum("allocated_amount"))
        return result["total"] or 0

    @property
    def remaining_amount(self):
        """
        Budget still available to spend for this grant.

        Calculated: total_amount - utilized_amount

        Return Value:
            Decimal: Can be positive (budget remains), zero (fully spent),
                     negative (overspent—should not happen with proper validation).

        Used By:
            - grant_detail template: Display "₹4,000 remaining"
            - _validate_allocations: Check if new allocation fits (remaining >= allocation)
            - Budget status display (red if < 0, yellow if < 20%, green if > 20%)

        Examples:
            - Total ₹10,000, spent ₹6,000: remaining = ₹4,000
            - Total ₹10,000, spent ₹10,000: remaining = ₹0 (fully utilized)
            - Total ₹10,000, spent ₹11,000: remaining = -₹1,000 (overspent—bug!)

        Edge Case:
            If total_amount is zero (placeholder grant), remaining = 0.
            Prevents division by zero in burn_rate calculation.

        Related:
            See burn_rate for percentage view of utilization.
        """
        return self.total_amount - self.utilized_amount

    @property
    def burn_rate(self):
        """
        Percentage of grant budget spent so far (0.0 to 100.0).

        Calculated: (utilized_amount / total_amount) * 100
        Rounded to 1 decimal place for UI display.

        Return Value:
            Float: Percentage (e.g., 60.5, 100.0, 0.0).
            Never negative (expenses always positive).
            Never exceeds 100.0 (with proper validation).
            Returns 0 if total_amount == 0 (edge case, placeholder grant).

        Used By:
            - Grant list/detail templates: Display "60.5% spent"
            - Progress bars: Color code by percentage
            - Spending dashboards: Sort/filter by burn rate
            - Financial reports: Track grant utilization trends

        Examples:
            - Total ₹10,000, spent ₹0: burn_rate = 0.0%
            - Total ₹10,000, spent ₹5,000: burn_rate = 50.0%
            - Total ₹10,000, spent ₹6,050: burn_rate = 60.5%
            - Total ₹10,000, spent ₹10,000: burn_rate = 100.0%
            - Total ₹0 (placeholder): burn_rate = 0 (prevents div by zero)

        Interpretation:
            - 0-30%: Spending just started, on track
            - 30-70%: Active spending, normal pace
            - 70-90%: Approaching limit, may need reallocations
            - 90-100%: Nearly exhausted, freeze new allocations
            - 100%+: Overspent (validation failure—shouldn't happen)

        Performance:
            Calls utilized_amount and total_amount, both O(1) simple math.
            The expensive part is utilized_amount (which has DB query).
            Caching not implemented (would invalidate on every allocation change).

        Rounding:
            Uses round(..., 1) for 1 decimal place.
            Examples: 60.52 → 60.5, 60.55 → 60.6

        Design Philosophy:
            Burn rate is a READ-ONLY metric, never stored in DB.
            Computed on-demand from live allocation data.
            Ensures accuracy: always reflects current spending state.
        """
        if self.total_amount == 0:
            return 0
        return round((self.utilized_amount / self.total_amount) * 100, 1)
