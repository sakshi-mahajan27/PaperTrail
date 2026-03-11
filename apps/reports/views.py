from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum

from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.expenses.models import Expense, ExpenseAllocation
from apps.compliance.models import ComplianceDocument


@login_required
def report_index(request):
    from django.urls import reverse
    report_cards = [
        ("Donor-wise Expenses", reverse("reports:donor_expense"), "bi-person-lines-fill", "Total expenses broken down by each donor."),
        ("Grant Utilization", reverse("reports:grant_utilization"), "bi-wallet2", "Budget vs. utilized amounts for all grants."),
        ("Financial Summary", reverse("reports:financial_summary"), "bi-bar-chart-line", "High-level financial overview."),
        ("Compliance Status", reverse("reports:compliance_status"), "bi-shield-check", "Current status of all compliance certificates."),
        ("Expense Ledger", reverse("reports:expense_ledger"), "bi-receipt", "Full chronological list of all expenses."),
    ]
    return render(request, "reports/report_index.html", {"report_cards": report_cards})


@login_required
def donor_expense_report(request):
    donors = Donor.objects.filter(is_active=True).prefetch_related(
        "grants__allocations__expense"
    )
    rows = []
    for donor in donors:
        total = ExpenseAllocation.objects.filter(
            grant__donor=donor, expense__is_active=True
        ).aggregate(t=Sum("allocated_amount"))["t"] or 0
        rows.append({"donor": donor, "total": total})
    return render(request, "reports/donor_expense_report.html", {"rows": rows})


@login_required
def grant_utilization_report(request):
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    return render(request, "reports/grant_utilization_report.html", {"grants": grants})


@login_required
def financial_summary_report(request):
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
def compliance_status_report(request):
    docs = ComplianceDocument.objects.all()
    return render(request, "reports/compliance_status_report.html", {"docs": docs})


@login_required
def expense_ledger_report(request):
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
