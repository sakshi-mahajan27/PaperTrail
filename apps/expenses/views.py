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
    Cross-formset validation:
    1. Sum of allocations must equal expense total.
    2. Each expense_date must be within the grant's active period.
    3. Grant budget must not be exceeded.
    Returns a list of error strings (empty = OK).
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
            if not (grant.start_date <= expense.expense_date <= grant.end_date):
                errors.append(
                    f"Expense date {expense.expense_date} is outside the grant "
                    f"'{grant.name}' period ({grant.start_date} – {grant.end_date})."
                )
            # Budget check: remaining + current allocation for this grant
            existing_alloc = ExpenseAllocation.objects.filter(
                grant=grant, expense__is_active=True
            ).exclude(expense=expense).aggregate(
                used=__import__("django.db.models", fromlist=["Sum"]).Sum("allocated_amount")
            )["used"] or Decimal("0")
            if existing_alloc + amount > grant.total_amount:
                errors.append(
                    f"Allocation of ₹{amount} to '{grant.name}' exceeds the available budget "
                    f"(₹{grant.total_amount - existing_alloc} remaining)."
                )

    if total != expense.total_amount:
        errors.append(
            f"Sum of allocations (₹{total}) must equal the total expense amount (₹{expense.total_amount})."
        )

    return errors


@login_required
@role_required("admin", "finance", "auditor")
def expense_list(request):
    expenses = Expense.objects.filter(is_active=True).select_related("created_by").prefetch_related("allocations__grant")
    return render(request, "expenses/expense_list.html", {"expenses": expenses})


@login_required
@role_required("admin", "finance", "auditor")
def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk, is_active=True)
    return render(request, "expenses/expense_detail.html", {"expense": expense})


@login_required
@finance_required
def expense_create(request):
    form = ExpenseForm(request.POST or None, request.FILES or None)
    formset = AllocationFormSet(request.POST or None, prefix="allocations")

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            # Validate cross-formset rules
            alloc_errors = _validate_allocations(expense, formset)
            if alloc_errors:
                for err in alloc_errors:
                    messages.error(request, err)
            else:
                with transaction.atomic():
                    expense.save()
                    formset.instance = expense
                    formset.save()
                messages.success(request, "Expense recorded successfully.")
                return redirect("expenses:expense_detail", pk=expense.pk)

    return render(request, "expenses/expense_form.html", {
        "form": form,
        "formset": formset,
        "title": "Record Expense",
    })


@login_required
@finance_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, is_active=True)
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=expense)
    formset = AllocationFormSet(request.POST or None, instance=expense, prefix="allocations")

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            expense = form.save(commit=False)
            alloc_errors = _validate_allocations(expense, formset)
            if alloc_errors:
                for err in alloc_errors:
                    messages.error(request, err)
            else:
                with transaction.atomic():
                    expense.save()
                    formset.save()
                messages.success(request, "Expense updated successfully.")
                return redirect("expenses:expense_detail", pk=expense.pk)

    return render(request, "expenses/expense_form.html", {
        "form": form,
        "formset": formset,
        "title": "Edit Expense",
        "object": expense,
    })


@login_required
@role_required("admin", "finance")
def expense_delete(request, pk):
    messages.error(request, "Expense deletion is not allowed for this role policy.")
    return redirect("expenses:expense_list")
