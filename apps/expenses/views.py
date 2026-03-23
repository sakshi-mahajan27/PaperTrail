from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction

from .models import Expense, ExpenseAllocation
from .forms import ExpenseForm, AllocationFormSet
from apps.accounts.decorators import role_required, finance_required


def _validate_allocations(expense, formset):
    """
    Cross-formset validation for expense allocations.

    This critical function validates that:
    1. Sum of allocations equals expense total (no over/under allocation)
    2. Each expense_date is within the grant's active period
    3. Grant budget is not exceeded by this allocation

    This is the core BUDGET ENFORCEMENT logic - prevents spending beyond
    what donors have authorized for each grant.

    Args:
        expense (Expense): The expense being allocated (may not be saved yet)
        formset (AllocationFormSet): Collection of allocation forms

    Returns:
        list: Error strings. Empty list = validation passed.

    Validation Errors Checked:
        1. ALLOCATION SUM MISMATCH
           Error: "Sum of allocations (₹{total}) must equal the total expense (₹{amount})"
           Why: Prevents orphaning money or double-counting

        2. DATE OUT OF GRANT PERIOD  
           Error: "Expense date {date} is outside grant '{name}' period ({start} - {end})"
           Why: Expenses must occur during the period donor authorized

        3. BUDGET EXCEEDED
           Error: "Allocation of ₹{amount} to '{grant}' exceeds available budget..."
           Why: Each grant has total_amount; can't spend more than authorized

    Implementation:
        1. Initialize total = 0.00
        2. For each allocation form in formset:
           - Skip if DELETE checked or not filled
           - Get grant and allocated_amount
           - Add to running total
           - Check date within grant period (start_date <= expense_date <= end_date)
           - Check remaining grant budget (existing + this allocation <= grant.total_amount)
        3. After loop, verify sum equals expense.total_amount
        4. Return list of error strings (empty if all valid)

    Query Explanation:
        ```python
        query = ExpenseAllocation.objects.filter(
            grant=grant, expense__is_active=True
        )
        if expense.pk:  # On edit, exclude current expense from other allocations
            query = query.exclude(expense=expense)
        existing_alloc = query.aggregate(
            used=Sum("allocated_amount")
        )["used"] or 0
        ```
        This calculates how much of the grant's budget is already used
        (excluding current expense if editing). Total budget check:
        existing_alloc + allocated_amount <= grant.total_amount

    Why Not Just Use Model Validation:
        - Can't validate formset totals at model/form level
        - Need context of all allocations together (not individually)
        - Budget check needs related ExpenseAllocation query
        - View-level validation is only way to achieve this

    Called By:
        - expense_create view: After formset.is_valid()
        - expense_edit view: After formset.is_valid()

    Example Usage:
        if form.is_valid() and formset.is_valid():
            expense = form.save(commit=False)
            alloc_errors = _validate_allocations(expense, formset)
            if not alloc_errors:
                # Safe to save
                expense.save()
                formset.save()
            else:
                # Show errors to user, don't save

    Notes:
        - Works even if expense.pk is None (create case)
        - Handles Decimal arithmetic correctly (no floating point errors)
        - Returns empty list if ALL validation passes
        - Errors are user-friendly (reference grant names, dates, amounts)
    """
    errors = []
    total = Decimal("0")

    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        grant = form.cleaned_data.get("grant")
        amount = form.cleaned_data.get("allocated_amount", Decimal("0"))
        total += amount

        if grant and expense.expense_date:
            # Validate 1: Expense date must fall within grant period
            if not (grant.start_date <= expense.expense_date <= grant.end_date):
                errors.append(
                    f"Expense date {expense.expense_date} is outside the grant "
                    f"'{grant.name}' period ({grant.start_date} – {grant.end_date})."
                )
            # Validate 2: Grant budget must not be exceeded
            query = ExpenseAllocation.objects.filter(
                grant=grant, expense__is_active=True
            )
            # Only exclude current expense if it has been saved (has a pk)
            if expense.pk:
                query = query.exclude(expense=expense)
            existing_alloc = query.aggregate(
                used=__import__("django.db.models", fromlist=["Sum"]).Sum("allocated_amount")
            )["used"] or Decimal("0")
            if existing_alloc + amount > grant.total_amount:
                errors.append(
                    f"Allocation of ₹{amount} to '{grant.name}' exceeds the available budget "
                    f"(₹{grant.total_amount - existing_alloc} remaining)."
                )

    # Validate 3: Sum of all allocations must equal expense total
    if total != expense.total_amount:
        errors.append(
            f"Sum of allocations (₹{total}) must be equal the total expense amount (₹{expense.total_amount})."
        )

    return errors


@login_required
@role_required("admin", "finance", "auditor")
def expense_list(request):
    """
    Display a list of all active expenses with allocation details.

    All authenticated users (admin, finance, auditor) can view expenses.
    Shows each expense with its creation date, amount, creator, and allocations.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Response:
        200 HTML table of all active expenses

    Template Used:
        expenses/expense_list.html

    Context Variables:
        expenses (QuerySet): All active (is_active=True) expenses

    Query Optimizations:
        - select_related("created_by"): Fetch user in single JOIN
        - prefetch_related("allocations__grant"): Fetch allocations + grants
        - Allows template to access expense.created_by.username and
          allocation.grant.name without extra queries

    Displayed Fields:
        - Expense title and amount
        - Expense date
        - Creator (who recorded the expense)
        - Allocations (which grants benefit from this expense)
        - Creation timestamp

    Links/Actions:
        - View expense detail (full info + allocations)
        - Edit expense (Finance Manager only, enforced in edit view)

    Notes:
        - Soft-deleted expenses (is_active=False) never shown
        - All roles can view (read-only for auditors)
        - Most recent expenses shown first (ordered by expense_date desc)
    """
    expenses = Expense.objects.filter(is_active=True).select_related("created_by").prefetch_related("allocations__grant")
    return render(request, "expenses/expense_list.html", {"expenses": expenses})


@login_required
@role_required("admin", "finance", "auditor")
def expense_detail(request, pk):
    """
    Display full details of a single expense with allocations.

    Shows complete expense record: title, amount, date, description, receipt,
    and all allocations to grants.

    Request Method:
        GET only

    Path Parameters:
        pk (int): Primary key of Expense to display

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Response:
        - 200 HTML detail page
        - 404 If expense doesn't exist or is inactive

    Template Used:
        expenses/expense_detail.html

    Context Variables:
        expense: The Expense instance

    Displayed Information:
        - Title, total amount, expense date
        - Description field
        - Receipt file link (for download)
        - Allocations table (grant name, amount for each)
        - Created by (user who recorded)
        - Timestamps (created/updated)

    Links/Actions:
        - Edit expense (if Finance Manager)
        - Download receipt
        - Back to expense list

    Notes:
        - Soft-deleted expenses (is_active=False) result in 404
        - Uses get_object_or_404 for graceful missing record handling
    """
    expense = get_object_or_404(Expense, pk=pk, is_active=True)
    return render(request, "expenses/expense_detail.html", {"expense": expense})


@login_required
@finance_required
def expense_create(request):
    """
    Create a new expense record with allocations to grants.

    Finance Manager only view. Presents expense form and allocation formset.
    On submit, validates that allocations sum correctly and fit grant budgets,
    then saves all in a single transaction (all-or-nothing).

    Request Method:
        GET: Display empty forms
        POST: Create expense and allocations after validation

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Forms Used:
        ExpenseForm: Main expense details
        AllocationFormSet: Collection of grant allocations

    Response:
        - 200 Display forms on GET
        - 302 Redirect to expense_detail on success
        - 200 Display forms with errors on POST failure

    Template Used:
        expenses/expense_form.html

    Context Variables:
        form: ExpenseForm instance
        formset: AllocationFormSet instance
        title: "Record Expense"
        alloc_errors: List of allocation validation errors (if any)

    Validation Flow:
        1. Form validation (form.is_valid()):
           - clean_receipt(): Receipt must exist
           - clean(): is_compliant() check (compliance gate)
        2. Formset validation (formset.is_valid()):
           - Each allocation form validates
           - Grant must exist and be active
           - Amount must be decimal
        3. View-level validation (_validate_allocations):
           - Allocations sum must equal expense total
           - Expense date within grant period
           - Grant budget not exceeded
        4. If all pass: Save in transaction.atomic()

    Success Flow:
        1. Finance Manager fills expense details
        2. Selected grants and amounts in formset rows
        3. Submits POST
        4. All validations pass
        5. Expense saved (created_by = request.user)
        6. All allocations saved
        7. Message: "Expense recorded successfully."
        8. Redirect to expense_detail
        9. Audit logs created (by signals)

    Error Handling:
        - ExpenseForm errors: Displayed with form
        - Formset errors: Displayed per form
        - Allocation errors: Listed in alloc_errors context
        - Compliance errors: "Cannot create expense. Certificates missing/expired."
        - Budget errors: "Allocation exceeds grant budget"

    Budget Enforcement:
        If grant has ₹10,000 budget and ₹6,000 already spent:
        - User tries to allocate ₹5,000 → Error: Only ₹4,000 available
        - Prevents overspending against donor budget

    Transaction Safety:
        Uses transaction.atomic():
        - If error after expense saved, all rolled back
        - If formset.save() fails, expense rolled back too
        - Prevents partial/orphaned data

    Notes:
        - Receipt file required (enforced in form)
        - At least 1 allocation required (formset min_num=1)
        - created_by set here (not from form)
        - is_active=True by default
        - Audit trail automatic (signals.py)
    """
    form = ExpenseForm(request.POST or None, request.FILES or None)
    formset = AllocationFormSet(request.POST or None, prefix="allocations")
    alloc_errors = []

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            # Validate cross-formset rules
            alloc_errors = _validate_allocations(expense, formset)
            if not alloc_errors:
                with transaction.atomic():
                    expense.save()
                    formset.instance = expense
                    formset.save()
                messages.success(request, "Expense recorded successfully.")
                return redirect("expenses:expense_detail", pk=expense.pk)
            else:
                # Add allocation validation errors as messages
                for err in alloc_errors:
                    messages.error(request, err)

    return render(request, "expenses/expense_form.html", {
        "form": form,
        "formset": formset,
        "title": "Record Expense",
        "alloc_errors": alloc_errors,
    })


@login_required
@finance_required
def expense_edit(request, pk):
    """
    Edit an existing expense record.

    Finance Manager can update expense details, receipt file, and reallocate
    to different grants. Uses same validation as create (compliance check,
    budget enforcement).

    Request Method:
        GET: Display pre-populated forms
        POST: Update expense and allocations

    Path Parameters:
        pk (int): Primary key of Expense to edit

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Forms Used:
        ExpenseForm: Update expense details
        AllocationFormSet: Update allocations

    Response:
        - 200 Display forms on GET or error
        - 302 Redirect to expense_detail on success
        - 404 If expense doesn't exist or is inactive

    Template Used:
        expenses/expense_form.html

    Context Variables:
        form: ExpenseForm instance, pre-filled
        formset: AllocationFormSet instance, pre-populated
        title: "Edit Expense"
        object: The Expense being edited
        alloc_errors: Allocation errors (if any)

    Editable Fields:
        Expense:
        - title: Can rename expense
        - total_amount: Can adjust (budget re-validation happens)
        - expense_date: Can correct (grant period re-validation)
        - description: Add/update notes
        - receipt: Can replace file

        Allocations:
        - grant: Change which grants benefit
        - allocated_amount: Adjust allocation amounts
        - Delete allocations (uncheck DELETE boxes)
        - Add allocations (use extra blank rows)

    Preserved Fields:
        - created_by: Never changes (who originally entered)
        - created_at: Never changes
        - is_active: Cannot edit here (see soft delete comment)

    Budget Re-Validation (Edit Case):
        When editing, _validate_allocations() excludes the current expense:
        ```python
        if expense.pk:
            query = query.exclude(expense=expense)
        ```
        This allows re-allocating the same expense to different grant splits
        without double-counting existing allocation.

        Example:
        - Original: Expense ₹10,000. Grant A budget ₹5,000 used.
        - Edit: Reallocate to Grant B
        - Check won't fail because original allocation to Grant A is excluded

    Success Flow:
        1. Finance Manager navigates to edit expense
        2. Updates amount, date, or allocations
        3. Submits POST
        4. All validations pass
        5. Expense updated
        6. Allocations updated
        7. Message: "Expense updated successfully."
        8. Redirect to expense_detail
        9. Audit logs created (what changed)

    Notes:
        - Uses get_object_or_404 (handles missing/inactive)
        - updated_at auto-refreshed (auto_now=True)
        - Soft delete preserves edit history
        - Audit trail shows all field changes (via AuditLog)
        - Compliance check still enforced (no expenses if not compliant)
    """
    expense = get_object_or_404(Expense, pk=pk, is_active=True)
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=expense)
    formset = AllocationFormSet(request.POST or None, instance=expense, prefix="allocations")
    alloc_errors = []

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            expense = form.save(commit=False)
            alloc_errors = _validate_allocations(expense, formset)
            if not alloc_errors:
                with transaction.atomic():
                    expense.save()
                    formset.save()
                messages.success(request, "Expense updated successfully.")
                return redirect("expenses:expense_detail", pk=expense.pk)
            else:
                # Add allocation validation errors as messages
                for err in alloc_errors:
                    messages.error(request, err)

    return render(request, "expenses/expense_form.html", {
        "form": form,
        "formset": formset,
        "title": "Edit Expense",
        "object": expense,
        "alloc_errors": alloc_errors,
    })


@login_required
@role_required("admin", "finance")
def expense_delete(request, pk):
    """
    Prevent expense deletion.

    Role policy: Expenses cannot be deleted. Show error message and redirect.
    This protects audit trail integrity - expenses must be preserved for audits.

    Request Method:
        GET: Show error and redirect
        POST: Show error and redirect

    Response:
        302 Redirect to expense_list with error message

    Message:
        "Expense deletion is not allowed for this role policy."

    Why No Deletion?
        - Breaks audit trail (expenses historically linked to grant budgets)
        - Violates NGO compliance (expensehistory must be preserved)
        - Could orphan allocations and confuse budget calculations
        - Soft delete (is_active=False) is alternative if needed

    Alternative (If Future Need):
        - Implement soft delete view (set is_active=False)
        - Optionally implement HARD delete for admins (very careful)
        - Current implementation prevents accidental deletion

    Notes:
        - Accessed if user tries /expense/{pk}/delete
        - Prevents both GET and POST (safe either way)
        - Message displayed in Django messages framework
    """
    messages.error(request, "Expense deletion is not allowed for this role policy.")
    return redirect("expenses:expense_list")
