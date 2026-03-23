from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from apps.accounts.decorators import report_required

from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.expenses.models import Expense, ExpenseAllocation
from apps.compliance.models import ComplianceDocument


@login_required
@report_required
def report_index(request):
    """
    Main reports dashboard with links to all available reports.

    Finance Manager and Auditor only view. Displays a card-based interface
    listing all reports with descriptions and links.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML dashboard with report cards

    Template Used:
        reports/report_index.html

    Context Variables:
        report_cards (list): List of tuples:
            - (title, url, icon, description) for each report

    Reports Available:
        1. Donor-wise Expenses
           URL: /reports/donor-expense/
           Icon: bi-person-lines-fill (Bootstrap icon)
           Description: "Total expenses broken down by each donor."
           Shows: Total amount spent from each donor's grants

        2. Grant Utilization
           URL: /reports/grant-utilization/
           Icon: bi-wallet2
           Description: "Budget vs. utilized amounts for all grants."
           Shows: Each grant with total, spent, remaining, burn rate

        3. Financial Summary
           URL: /reports/financial-summary/
           Icon: bi-bar-chart-line
           Description: "High-level financial overview."
           Shows: Total grants, total expenses, net unspent, grant breakdown

        4. Compliance Status
           URL: /reports/compliance-status/
           Icon: bi-shield-check
           Description: "Current status of all compliance certificates."
           Shows: FCRA, 80G, 12A status (green/yellow/red)

        5. Expense Ledger
           URL: /reports/expense-ledger/
           Icon: bi-receipt
           Description: "Chronological view of all expenses for audit review."
           Shows: All expenses, dates, amounts, allocations, creators

    Usage:
        Report Index is a gateway page. Users click on a report card to
        navigate to that specific report.

    Notes:
        - All links use Django reverse() for URL generation
        - Icons are Bootstrap Icons (CSS classes)
        - Descriptions are user-friendly explanations
        - No data fetching here (just links)
    """
    from django.urls import reverse
    report_cards = [
        ("Donor-wise Expenses", reverse("reports:donor_expense"), "bi-person-lines-fill", "Total expenses broken down by each donor."),
        ("Grant Utilization", reverse("reports:grant_utilization"), "bi-wallet2", "Budget vs. utilized amounts for all grants."),
        ("Financial Summary", reverse("reports:financial_summary"), "bi-bar-chart-line", "High-level financial overview."),
        ("Compliance Status", reverse("reports:compliance_status"), "bi-shield-check", "Current status of all compliance certificates."),
        ("Expense Ledger", reverse("reports:expense_ledger"), "bi-receipt", "Chronological view of all expenses for audit review."),
    ]
    return render(request, "reports/report_index.html", {"report_cards": report_cards})


@login_required
@report_required
def donor_expense_report(request):
    """
    Donor-wise expense breakdown: total spending per donor.

    Shows total amount spent from each donor's grants.
    Useful for accountability reporting to donors and tracking
    who has spent the most.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML table of donors with total spending

    Template Used:
        reports/donor_expense_report.html

    Context Variables:
        rows (list): List of dicts with:
            - donor: Donor instance
            - total: Total amount spent from this donor's grants
        grand_total (Decimal): Sum of all donor totals

    Query Logic:
        For each active donor:
        1. Sum all ExpenseAllocation amounts where grant.donor = this donor
        2. Only include active expenses (expense__is_active=True)
        3. Store in rows list

        Implemented:
        ```python
        donors = Donor.objects.filter(is_active=True).prefetch_related(
            "grants__allocations__expense"
        )
        for donor in donors:
            total = ExpenseAllocation.objects.filter(
                grant__donor=donor, expense__is_active=True
            ).aggregate(t=Sum("allocated_amount"))["t"] or 0
            rows.append({"donor": donor, "total": total})
        ```

    Query Optimization:
        - prefetch_related("grants__allocations__expense"):
          Avoids N+1 queries when accessing donor.grants in template
        - Still requires one aggregate query per donor (unavoidable with Django ORM)
        - Alternative: Use database aggregation for better performance

    Displayed Information:
        - Donor name
        - Donor type (individual/organization/government/corporate)
        - PAN (if individual/organization)
        - Total amount spent from this donor's grants
        - Link to donor detail (for more info)

    Rows are typically sorted by:
        - Total spending (highest first), or
        - Donor name (alphabetical), or
        - Donor type

    Grand Total:
        Sum of all donor totals (should equal total expenses).
        Verification: grand_total = sum(expense.total_amount for all active expenses)

    Use Cases:
        - Accountability: Report to board on spending per donor
        - Budget review: See which donors' budgets are most active
        - Annual reports: Show donor grants spent each year
        - Compliance: Ensure spending aligns with donor agreements

    Data Interpretation:
        - Primary query: ExpenseAllocation (join point of donors and expenses)
        - Filter: grant__donor = each donor (trace back to grant owner)
        - Filter: expense__is_active=True (only actual spending, not deletions)
        - Soft-deleted expenses excluded automatically

    Notes:
        - Soft-deleted donors (is_active=False) excluded
        - Soft-deleted expenses excluded
        - Soft-deleted grants' allocations still counted (grant is_active not filtered)
        - One allocaton row per expense splitted across grants
    """
    donors = Donor.objects.filter(is_active=True).prefetch_related(
        "grants__allocations__expense"
    )
    rows = []
    for donor in donors:
        total = ExpenseAllocation.objects.filter(
            grant__donor=donor, expense__is_active=True
        ).aggregate(t=Sum("allocated_amount"))["t"] or 0
        rows.append({"donor": donor, "total": total})
    grand_total = sum(r["total"] for r in rows)
    return render(request, "reports/donor_expense_report.html", {"rows": rows, "grand_total": grand_total})


@login_required
@report_required
def grant_utilization_report(request):
    """
    Grant utilization report: budget vs spent per grant.

    Shows each grant with total budget, amount spent (utilized),
    remaining budget, and burn rate percentage.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML table of grants with utilization metrics

    Template Used:
        reports/grant_utilization_report.html

    Context Variables:
        grants (QuerySet): All active grants with related donor data

    Query Optimization:
        ```python
        grants = Grant.objects.filter(is_active=True).select_related("donor")
        ```
        - select_related("donor"): Fetch donor in single JOIN
        - Avoids N+1 when displaying donor names

    Displayed Information (Per Grant Row):
        - Donor name (from FK)
        - Grant name
        - Grant status (pending/active/closed)
        - Total budget (total_amount)
        - Amount utilized (sum of ExpenseAllocation amounts)
        - Remaining budget (total - utilized)
        - Burn rate (utilized / total * 100%)
        - Progress bar visualization (color-coded by burn rate)

    Metrics Calculation:
        Each displayed metric is a @property on Grant model:

        - utilized_amount: @property
          Sum of ExpenseAllocation.allocated_amount for this grant
          Query happens per grant (N+1 unavoidable without heavy optimization)

        - remaining_amount: @property
          total_amount - utilized_amount
          Simple arithmetic, no query

        - burn_rate: @property
          (utilized_amount / total_amount) * 100
          Useful for at-a-glance status (0%=not started, 100%=complete)

    Color Coding (UI):
        - Green: burn_rate 0-70% (normal spending pace)
        - Yellow: burn_rate 70-90% (approaching limit)
        - Red: burn_rate > 90% (nearly exhausted)

    Performance Note (IMPORTANT):
        For large datasets (100+ grants), this report may be slow because:
        - Each grant accesses utilized_amount (@property) which queries DB
        - Results in 1 query (fetch all grants) + N queries (one per grant)
        - Total: 1 + N queries

        Optimization Needed:
        - Annotate aggregate in main query using Django ORM annotate()
        - Alternative: Use raw aggregation query

    Use Cases:
        - Budget monitoring: Track spending pace across all grants
        - Rebalancing: Identify overspent/underspent grants
        - Donor relations: Report progress to donors on their grants
        - Financial planning: See remaining budget for new initiatives
        - Year-end: Final grant utilization summary

    Data Interpretation:
        - 100% burn rate = fully spent (no more budget)
        - ~80% burn rate = standard (typical monthly-end state)
        - <50% burn rate = early spending (pacing well)
        - 0% burn rate = new grant (not yet allocated)

    Status Context:
        - PENDING: Just created, no spending expected
        - ACTIVE: Normal usage, burning budget
        - CLOSED: Finished, no new allocations

    Notes:
        - Soft-deleted grants (is_active=False) excluded
        - Soft-deleted expenses excluded from utilized_amount
        - Grants can show negative remaining (validation failure—shouldn't happen)
    """
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    return render(request, "reports/grant_utilization_report.html", {"grants": grants})


@login_required
@report_required
def financial_summary_report(request):
    """
    High-level financial summary: total grants, spending, and net unspent budget.

    Provides executive-level view of financial health: how much money was
    given (total grants), how much has been spent (total expenses), and how
    much remains unallocated.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML dashboard with aggregate metrics and grant breakdown

    Template Used:
        reports/financial_summary_report.html

    Context Variables:
        total_grants (Decimal): Sum of all active grant budgets
        total_expenses (Decimal): Sum of all active expense totals
        net_unspent (Decimal): total_grants - total_expenses
        grants (QuerySet): All active grants for breakdown table

    Aggregate Queries:
        ```python
        total_grants = Grant.objects.filter(is_active=True).aggregate(
            t=Sum("total_amount")
        )["t"] or 0

        total_expenses = Expense.objects.filter(is_active=True).aggregate(
            t=Sum("total_amount")
        )["t"] or 0

        net_unspent = total_grants - total_expenses
        ```

    Key Metrics Displayed:

        1. Total Grants
           Sum of all grant total_amount fields
           Represents total money donors have authorized
           Example: ₹50,00,000

        2. Total Expenses
           Sum of all expense total_amount fields
           Represents total money NGO has spent
           Example: ₹30,00,000

        3. Net Unspent Budget
           total_grants - total_expenses
           Money still available for allocation
           Example: ₹20,00,000

        4. Utilization Rate
           (total_expenses / total_grants) * 100
           Overall burn rate across all donors
           Example: 60% → 40% still available

    Additional Breakdown:
        Table showing each grant with:
        - Donor name
        - Grant name
        - Status
        - Budget
        - Burned | Remaining | Rate

    Use Cases:
        - Board reports: "NGO has ₹50L authorized, spent ₹30L, ₹20L remains"
        - Financial health: Show donors/board that spending is on pace
        - Year-end reconciliation: Verify total allocations match expense totals
        - Cash flow planning: "We have ₹20L unspent, need to plan use"

    Data Interpretation:
        net_unspent > 0: Normal (budget remaining)
        net_unspent == 0: Fully utilized (all grants spent)
        net_unspent < 0: Overspent (shouldn't happen with proper validation)

    Relationship to Other Reports:
        - Donor Expense: Shows breakdown by donor
        - Grant Utilization: Shows breakdown by grant
        - Financial Summary: High-level view of all three

    Query Optimization:
        - aggregate() with Sum: Single database query per metric
        - select_related("donor"): Efficient FK join for grant breakdown
        - Very efficient: Only 3 aggregate queries + 1 grant list query

    Notes:
        - Soft-deleted grants excluded (is_active=True)
        - Soft-deleted expenses excluded (is_active=True)
        - Soft-deleted donors still shown (donor is_active not checked)
        - Net unspent calculation simple arithmetic (no queries)
    """
    total_grants = Grant.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    total_expenses = Expense.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    net_unspent = total_grants - total_expenses
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    context = {
        "total_grants": total_grants,
        "total_expenses": total_expenses,
        "net_unspent": net_unspent,
        "grants": grants,
    }
    return render(request, "reports/financial_summary_report.html", context)


@login_required
@report_required
def compliance_status_report(request):
    """
    Compliance certificate status report: FCRA, 80G, 12A status.

    Shows current status of all NGO compliance certificates:
    - Certificate type (FCRA/80G/12A)
    - Expiration date
    - Days until expiry
    - Status color (green/yellow/red)
    - Alerts if approaching expiry

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML report showing all certificates with status

    Template Used:
        reports/compliance_status_report.html

    Context Variables:
        docs (QuerySet): All ComplianceDocument records (no filtering)

    Data Fetched:
        ```python
        docs = ComplianceDocument.objects.all()
        ```
        - Fetches all certificates (active and expired)
        - No exclusions—shows full compliance status

    Document Fields Displayed:
        - certificate_type: FCRA, 80G, or 12A
        - expiry_date: When certificate expires
        - uploaded_date: When document was uploaded
        - status: GREEN/YELLOW/RED (@property calculated)
        - status_label: Human-readable "Valid" / "Warning" / "Expired"
        - days_to_expiry: Days remaining until expiry
        - alert_style: CSS class for color-coding

    Status Logic (From ComplianceDocument.status property):
        - GREEN: > 180 days to expiry → Fully compliant ✓
        - YELLOW: ≤ 180 days to expiry → Warning, still valid ⚠️
        - RED: Expired (expiry_date < today) → Non-compliant ✗

    Visual Presentation (UI):
        Status badges colored:
        - Green background: Valid / Compliant
        - Yellow background: Warning / Approaching expiry
        - Red background: Expired / Non-compliant

    Business Context (NGO Regulatory):
        FCRA (Foreign Contribution Regulation Act):
        - Required for international donations
        - Issued by Ministry of Home Affairs
        - Expiry can be 2-5 years typically

        80G Certificate:
        - Required for Indian tax-deductible donations
        - Issued by Income Tax Department
        - Donors get income tax deduction
        - Expiry typically 5 years

        12A Certificate:
        - NGO tax exemption status
        - Issued by Income Tax Department
        - NGO gets exemption on income
        - Expiry typically 5 years

        All Three Must Be Valid:
        - If any expired (RED), NGO cannot:
          * Accept new donations (restrictions on receipts)
          * Create new grants (compliance gate blocks from grant_create)
          * Allocate new expenses (compliance gate in ExpenseForm)

    Critical Alert System:
        YELLOW status triggers:
        - send_yellow_alert_email_task (nightly via Celery)
        - Notifies admins to renew soon
        - But spending still allowed (yellow is "warning" not "block")

    Use Cases:
        - Compliance monitoring: Track expiry dates across all certs
        - Renewal planning: When to apply for new certificates
        - Audit readiness: Show compliance status to external auditors
        - Risk assessment: Identify RED certificates that need immediate action
        - Board reporting: "All certificates valid, 80G expires in 90 days"

    Renewal Checklist:
        For each RED certificate:
        1. Contact issuing authority (MHA for FCRA, ITD for 80G/12A)
        2. Apply for renewal (usually 3-6 months before expiry)
        3. Upload new certificate (via document_upload view)
        4. System auto-updates compliance status
        5. Any blocked operations now allowed again

    Data Interpretation:
        All GREEN: Full compliance ✓
        Any YELLOW: OK for now, start renewal process soon ⚠️
        Any RED: URGENT - cannot operate normally until renewed ✗

    Query Optimization:
        - No filters: Just fetch all documents
        - No joins/relationships: Single table query
        - Very efficient: Single database query

    Related Views/Functions:
        - document_upload: Upload new certificate (sets status)
        - document_edit: Update certificate details
        - is_compliant(): Checks if all GREEN/YELLOW (no RED)
        - get_compliance_issues(): Lists what's wrong
        - send_yellow_alert_email_task: Alerts if YELLOW

    Notes:
        - Fetches all documents (including very old ones)
        - May want to filter to recent/active only
        - Status computed on-the-fly (@property, not stored in DB)
        - days_to_expiry can be negative (for RED/expired)
    """
    docs = ComplianceDocument.objects.all()
    return render(request, "reports/compliance_status_report.html", {"docs": docs})


@login_required
@report_required
def expense_ledger_report(request):
    """
    Expense ledger: chronological view of all expenses with allocations.

    Provides audit trail of all spending: date, amount, description,
    allocations to grants, and who recorded the expense.

    Request Method:
        GET with optional grant filter

    Query Parameters:
        grant (optional): Filter by grant ID
            - Blank: Show all expenses
            - Grant_id: Show only expenses allocated to that grant

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager or Auditor role (@report_required)

    Response:
        200 HTML ledger table of expenses, optionally filtered

    Template Used:
        reports/expense_ledger_report.html

    Context Variables:
        expenses (QuerySet): All active expenses, filtered by grant if specified
        grants (QuerySet): All active grants (for filter dropdown)
        grant_filter (str): Current grant filter value (grant ID or "")

    Query Logic:
        Base query:
        ```python
        expenses = Expense.objects.filter(is_active=True).select_related(
            "created_by"
        ).prefetch_related(
            "allocations__grant__donor"
        ).order_by("expense_date")
        ```

        If grant filter provided:
        ```python
        expenses = expenses.filter(allocations__grant_id=grant_filter).distinct()
        ```

    Query Optimization:
        - select_related("created_by"): Fetch user in JOIN
        - prefetch_related("allocations__grant__donor"):
          Avoid N+1 when showing allocations + donor names
        - order_by("expense_date"): Chronological order
        - distinct(): Avoid duplicate rows if multiple allocations per expense

    Displayed Information (Per Expense Row):
        - Expense date (chronological)
        - Title/description
        - Total amount
        - Receipt file (with download link)
        - Creator (who recorded)
        - Allocations:
            * Grant name
            * Donor (from grant.donor)
            * Amount allocated to this grant
        - Created timestamp

    Filter Dropdown:
        Shows all active grants.
        Allows user to select one grant to view only expenses for that grant.
        Example: Select "Rural Education 2024" → see only expenses allocated to it.

    Use Cases:
        - Audit trail: Show auditors all expenses in order
        - Grant analysis: "What expenses were charged to this grant?"
        - Accountability: Prove every expense is documented and allocated
        - Year-end: Generate ledger for external auditors
        - Dispute resolution: "When was this expense recorded? Who recorded it?"
        - Compliance: Show that soft-deleted expenses are excluded

    Data Interpretation:
        - Chronological order: Expenses ordered by date (oldest first or newest first)
        - Allocations breakdown: Shows how each expense was split across grants
        - Total column: Should match sum of allocations (validated in _validate_allocations)
        - Creator: Shows user who logged the expense (audit accountability)

    Allocation Example:
        Expense: "Office Rent ₹10,000" for Jan 2024
        Allocations:
        - Grant A (Rural Education): ₹6,000
        - Grant B (Health Program): ₹4,000
        Total: ₹10,000 ✓

    Filter Mechanics:
        Grant filter uses allocations__grant_id lookup.
        If expense has multiple allocations (to multiple grants):
        - Selecting Grant A shows this expense
        - Also shows other allocations within same expense
        - Example: office rent allocated to A and B both shown when filtering A

    Performance Note:
        For large datasets (1000+ expenses), this report may be slow:
        - prefetch_related works well but still displays all data
        - Consider pagination (not currently implemented)
        - Alternative: CSV export for bulk external processing

    Data Exclusions:
        - Soft-deleted expenses (is_active=False) always excluded
        - Soft-deleted grants: allocations still shown (grant is_active not filtered)
        - Soft-deleted donors: still shown (FK preserved)

    CSV/Export Note:
        This view could be extended to export to CSV for:
        - External auditors
        - Donor reporting
        - Tax filing

    Notes:
        - Report is comprehensive (all expenses shown)
        - Filter helps narrow for specific grant analysis
        - Distinct() prevents row duplication from prefetch relationships
        - No pagination currently (may needed for large datasets)
    """
    expenses = Expense.objects.filter(is_active=True).select_related("created_by").prefetch_related(
        "allocations__grant__donor"
    ).order_by("expense_date")
    grant_filter = request.GET.get("grant", "")
    if grant_filter:
        expenses = expenses.filter(allocations__grant_id=grant_filter).distinct()
    grants = Grant.objects.filter(is_active=True)
    return render(request, "reports/expense_ledger_report.html", {
        "expenses": expenses,
        "grants": grants,
        "grant_filter": grant_filter,
    })
