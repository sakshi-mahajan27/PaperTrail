from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Grant
from .forms import GrantForm
from apps.accounts.decorators import role_required, finance_required
from apps.compliance.utils import is_compliant, get_compliance_issues


@login_required
@role_required("admin", "finance", "auditor")
def grant_list(request):
    """
    Display a list of all active grants with optional status filtering.

    All authenticated users (admin, finance, auditor) can view the grant list.
    List shows grant name, donor, budget, dates, and status.
    Optional filter by status (pending/active/closed).

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Query Parameters:
        status (optional): Filter by grant status
            - "" (empty): Show all active grants
            - "pending": Show only pending grants
            - "active": Show only active grants
            - "closed": Show only closed grants

    Response:
        200 HTML table of matching grants

    Template Used:
        grants/grant_list.html

    Context Variables:
        grants (QuerySet): Active grants (is_active=True), filtered by status if provided
        status_filter (str): Current status filter value (empty string if none)
        status_choices (list): All available status choices for UI filter dropdown

    Query Optimizations:
        - Filters: is_active=True, status filter
        - select_related("donor"): Fetch donor in single JOIN
            Prevents N+1 query when displaying donor names
        - Ordering: Newest grants first (ordered by -created_at in model)

    Filter Logic:
        ```python
        grants = Grant.objects.filter(is_active=True).select_related("donor")
        status_filter = request.GET.get("status", "")
        if status_filter:
            grants = grants.filter(status=status_filter)
        ```

    Displayed Fields:
        - Grant name (clickable to detail view)
        - Donor name (who authorized the grant)
        - Total budget amount
        - Start and end dates
        - Current status (pending/active/closed)
        - Burn rate % (calculated property)
        - Remaining budget (calculated property)

    Links/Actions:
        - View grant detail (full info + expense allocations)
        - Edit grant (Finance Manager only)
        - Close grant (Finance Manager only)

    Use Cases:
        - Finance Manager: See all grants, manage status transitions
        - Auditor: View grants to verify budget compliance
        - Admin: Oversight of all donor funding

    Notes:
        - Soft-deleted grants (is_active=False) never shown
        - Newest grants shown first
        - Status filter state preserved in URL (?status=active)
        - All roles can view (read-only for auditors)
    """
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    status_filter = request.GET.get("status", "")
    if status_filter:
        grants = grants.filter(status=status_filter)
    return render(request, "grants/grant_list.html", {
        "grants": grants,
        "status_filter": status_filter,
        "status_choices": Grant.STATUS_CHOICES,
    })


@login_required
@role_required("admin", "finance", "auditor")
def grant_detail(request, pk):
    """
    Display full details of a single grant with all allocations.

    Shows complete grant record: donor, budget, dates, purpose, status, and
    all expense allocations to this grant.

    Request Method:
        GET only

    Path Parameters:
        pk (int): Primary key of Grant to display

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Response:
        - 200 HTML detail page
        - 404 If grant doesn't exist or is inactive

    Template Used:
        grants/grant_detail.html

    Context Variables:
        grant (Grant): The grant being displayed
        allocations (QuerySet): All active expense allocations to this grant

    Query Optimizations:
        - get_object_or_404: Fetches grant, returns 404 if not found
        - allocations.filter(expense__is_active=True): Only active expenses
        - select_related("expense"): Fetch expense in single JOIN
            Avoids N+1 when displaying expense details in table

    Allocation Query:
        ```python
        allocations = grant.allocations.filter(
            expense__is_active=True
        ).select_related("expense")
        ```
        Shows expenses allocated to this grant (not other grants).

    Displayed Information:
        - Donor name (with link to donor detail)
        - Grant name and status
        - Budget info: total, spent (utilized), remaining
        - Progress: burn_rate % visualization
        - Date range: start_date to end_date
        - Purpose: why donor authorized this funding
        - Agreement file: download link (if provided)
        - Allocations table:
            * Which expenses
            * Amounts allocated from each
            * Dates expenses occurred
            * Running total

    Links/Actions:
        - View donor detail (who authorized grant)
        - Edit grant details (Finance Manager only)
        - Close grant (Finance Manager only)
        - View expense detail (for each allocation)
        - Back to grant list

    Use Cases:
        - Finance Manager: Monitor grant spending, check remaining budget
        - Auditor: Verify expense allocations match donor authorization
        - Admin: Review grant status and compliance

    Budget Summary (Displayed):
        - Total: ₹X
        - Allocated: ₹Y (sum of expense allocations)
        - Remaining: ₹(X-Y)
        - Burn Rate: Y/X * 100%
        - Status: Green (< 70%), Yellow (70-90%), Red (> 90%)

    Notes:
        - Soft-deleted grants (is_active=False) result in 404
        - Soft-deleted expenses (is_active=False) excluded from allocations list
        - Shows historical data (past allocations even if grant now closed)
    """
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    allocations = grant.allocations.filter(expense__is_active=True).select_related("expense")
    return render(request, "grants/grant_detail.html", {"grant": grant, "allocations": allocations})


@login_required
@finance_required
def grant_create(request):
    """
    Create a new grant record with compliance check.

    Finance Manager only view. On submit, checks is_compliant() before allowing
    grant creation. Prevents NGO from committing to new donor programs if
    certificates (FCRA, 80G, 12A) are missing or expired.

    Request Method:
        GET: Display empty form
        POST: Create grant after compliance check

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Response:
        - 200 Display form on GET
        - 302 Redirect to grant_list on success
        - 302 Redirect to grant_list on compliance failure (with error message)

    Template Used:
        grants/grant_form.html

    Context Variables:
        form (GrantForm): Empty form on GET, populated with errors on POST failure
        title: "Create Grant"

    Compliance Gate Logic:
        ```python
        if not is_compliant():
            issues = get_compliance_issues()
            messages.error(request, f"Cannot create a grant. Compliance issues: {' | '.join(issues)}")
            return redirect("grants:grant_list")
        ```

    Why Compliance Check?
        Donor agreement requires NGO to maintain certifications.
        - FCRA (Foreign Contribution Regulation Act): For international donations
        - 80G: For tax-deductible donations (domestic)
        - 12A: For income-tax exemption
        If any expired, NGO cannot legally commit to new spending.

    Compliance Success Criteria (from is_compliant):
        1. All 3 certificates exist in ComplianceDocument
        2. None are RED (expired—expiry_date < today)
        3. YELLOW (≤180 days to expiry) still allowed but flagged

    Failure Handling:
        IF not_compliant:
        - Show error message with specific issues
        - Redirect back to grant list (form not shown)
        - User cannot bypass—must fix compliance first

        EXAMPLE message:
        "Cannot create a grant. Compliance issues: FCRA expires in 45 days | 12A certificate missing"

    Success Flow:
        1. Finance Manager fills grant form
        2. Selects donor, sets budget, dates, purpose
        3. Submits POST
        4. is_compliant() check passes
        5. Form.clean() validates end_date > start_date
        6. Grant saved (status=PENDING by default)
        7. Message: "Grant created successfully."
        8. Redirect to grant_list
        9. Audit logged (created by which user)

    Form Fields:
        - donor: Select active donor
        - name: Grant name/title
        - total_amount: Budget in ₹
        - start_date, end_date: Date range for spending
        - purpose: What money is for
        - status: Default PENDING (can change in edit view)
        - agreement_file: Optional donor agreement

    Data Constraints:
        - Donor must be active (is_active=True)
        - End date must be after start date
        - Total amount must be positive (DecimalField)

    Notes:
        - Grant status starts as PENDING (must set to ACTIVE to use)
        - created_at auto-timestamp set by Django
        - is_active=True by default
        - NO created_by field (grants not tracked to individual manager)
        - Audit trail shows grant was created but not who created it
    """
    # COMPLIANCE GATE: NGO must have all certificates before committing to new funding
    if not is_compliant():
        issues = get_compliance_issues()
        messages.error(request, "Cannot create a grant. Compliance issues: " + " | ".join(issues))
        return redirect("grants:grant_list")

    form = GrantForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grant created successfully.")
        return redirect("grants:grant_list")
    return render(request, "grants/grant_form.html", {"form": form, "title": "Create Grant"})


@login_required
@finance_required
def grant_edit(request, pk):
    """
    Edit an existing grant record.

    Finance Manager can update grant details: name, donor, budget, dates,
    purpose, status, and agreement file.

    Request Method:
        GET: Display pre-populated form
        POST: Update grant

    Path Parameters:
        pk (int): Primary key of Grant to edit

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Response:
        - 200 Display form on GET or error
        - 302 Redirect to grant_detail on success
        - 404 If grant doesn't exist or is inactive

    Template Used:
        grants/grant_form.html

    Context Variables:
        form: GrantForm instance, pre-filled with grant data
        title: "Edit Grant"
        object: The Grant being edited

    Editable Fields:
        - name: Can rename grant
        - donor: Can change donor (rare but allowed)
        - total_amount: Can adjust budget (CAUTION: affects remaining budget)
        - start_date, end_date: Can correct date range
        - purpose: Can update purpose description
        - status: Can change status (pending → active → closed)
        - agreement_file: Can upload/replace document

    Preserved Fields:
        - created_at: Never changes (immutable creation timestamp)
        - is_active: Cannot edit here (use soft-delete if needed)

    Preserved by Update:
        - updated_at: Auto-refreshed when form.save() called

    Validation:
        Form-level (GrantForm.clean()):
        - end_date must be after start_date
        - Raises ValidationError if violated

        No View-Level Validation:
        - IMPORTANT: No is_compliant() check on edit
        - Allows updating grant even if compliance now broken
        - Rationale: Shouldn't prevent editing past data due to current issues

    Budget Edit Behavior (Care Required):
        If you increase total_amount:
        - remaining_amount increases (more budget available)
        - Example: ₹10,000 with ₹6,000 spent → edit to ₹15,000 → ₹9,000 remaining

        If you decrease total_amount below utilized_amount:
        - remaining_amount becomes negative (OVERSPENT)
        - Example: ₹10,000 with ₹6,000 spent → edit to ₹5,000 → ₹-1,000 remaining?!
        - Form doesn't prevent this—UI should warn

    Success Flow:
        1. Finance Manager navigates to edit grant
        2. Updates one or more fields
        3. Submits POST
        4. Form validation passes
        5. Grant updated in place
        6. Message: "Grant updated successfully."
        7. Redirect to grant_detail
        8. Audit logged (what changed)

    Allocation Impact:
        Editing a grant does NOT change existing allocations.
        - Expenses previously allocated remain allocated
        - Reallocating needs separate expense edit view

        Example:
        - Grant A: ₹10,000, edit to ₹15,000
        - Expense allocations to Grant A don't change
        - Just more budget room available now

    Status Transitions While Editing:
        Can change status while editing other fields:
        - PENDING → ACTIVE: Grant now accepting allocations
        - ACTIVE → CLOSED: Grant closed, no more new allocations
        - CLOSED → ACTIVE: Can reopen (rare)
        - PENDING → CLOSED: Possible but unusual

    Notes:
        - Uses get_object_or_404 (handles missing/inactive)
        - Form handles donor filtering (only active donors shown)
        - No created_by field (not tracked to individual)
        - Audit trail captures all field changes
        - Compliance check not re-enforced (allows editing even if compliance broken)
    """
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    form = GrantForm(request.POST or None, request.FILES or None, instance=grant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grant updated successfully.")
        return redirect("grants:grant_detail", pk=pk)
    return render(request, "grants/grant_form.html", {"form": form, "title": "Edit Grant", "object": grant})


@login_required
@finance_required
def grant_close(request, pk):
    """
    Close a grant (mark as no longer accepting allocations).

    Finance Manager only. Presents confirmation form. On POST, sets grant
    status to CLOSED. Prevents new expense allocations to this grant but
    preserves historical data.

    Request Method:
        GET: Display confirmation form
        POST: Change grant status to CLOSED

    Path Parameters:
        pk (int): Primary key of Grant to close

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Response:
        - 200 Display confirmation on GET
        - 302 Redirect to grant_list on POST success
        - 404 If grant doesn't exist or is inactive

    Template Used:
        grants/grant_confirm_close.html (confirmation page)

    Context Variables:
        grant: The Grant being closed

    Confirmation Flow:
        1. User clicks "Close Grant" link from grant_detail
        2. GET → Display: "Are you sure you want to close Grant X?"
           Shows grant details for confirmation
        3. User clicks "Yes, Close Grant" button
        4. POST → Close grant, redirect to grant_list

    What "Close" Means (Different from Delete):
        - Status changed: ACTIVE (or PENDING) → CLOSED
        - is_active remains True (not soft-deleted, just closed)
        - Allocations preserved: All expense allocations remain
        - Budget frozen: Can no longer add new allocations
        - Data preserved: Grant and its history visible in reports

    Why Close vs Delete?
        - Soft-delete (is_active=False) removes from normal views
        - "Close" (status=CLOSED) keeps in views but prevents changes
        - Allows auditing what happened to this grant after closure

    Post-Close Behavior:
        - New allocations blocked by view-level validation
        - Existing allocations still visible in grant_detail
        - Can still edit grant details (if needed to correct)
        - Cannot re-activate by same button (requires manual edit)

    Status Update:
        ```python
        grant.status = Grant.STATUS_CLOSED  # "closed"
        grant.save()
        ```
        - updated_at auto-refreshed
        - Change logged in AuditLog (status: active → closed)

    Success Message:
        "Grant '<name>' has been closed."
        Example: "Grant 'Rural Education 2024' has been closed."

    Use Cases:
        - Grant period ended: Jan 2024 grant expires Dec 31
        - Budget exhausted: All ₹10,000 spent, no more room
        - Program cancelled: Decision to stop this program
        - Donor withdrew: Donor requested grant revocation

    Cannot Reopen Via This View:
        To reopen a closed grant, use grant_edit view and change
        status back to ACTIVE manually.
        This discourages accidental re-opening without intent.

    Audit Trail:
        Closing logged as: status change from ACTIVE to CLOSED
        Shows: who closed it, when, previous/new status

    Notes:
        - Confirmation page prevents accidental closures
        - Only Finance Manager can close (prevents accidental admin clicks)
        - Closing doesn't affect existing allocations (historical data intact)
        - is_active remains True (grant not soft-deleted)
    """
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    if request.method == "POST":
        grant.status = Grant.STATUS_CLOSED
        grant.save()
        messages.success(request, f"Grant '{grant.name}' has been closed.")
        return redirect("grants:grant_list")
    return render(request, "grants/grant_confirm_close.html", {"grant": grant})
