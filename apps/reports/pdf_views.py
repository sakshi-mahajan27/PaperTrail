from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from django.utils.timezone import localtime
from apps.accounts.decorators import report_required

from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.expenses.models import Expense, ExpenseAllocation
from apps.compliance.models import ComplianceDocument

from .pdf_utils import render_pdf_response


@login_required
@report_required
def donor_expense_pdf(request):
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
    context = {
        "rows": rows,
        "grand_total": grand_total,
        "generated_on": localtime(timezone.now()).strftime("%d %b %Y, %H:%M"),
        "user": request.user,
    }
    return render_pdf_response(
        "reports/pdf/donor_expense_pdf.html",
        context,
        filename="donor_expense_report.pdf",
        request=request,
    )


@login_required
@report_required
def grant_utilization_pdf(request):
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    context = {
        "grants": grants,
        "generated_on": localtime(timezone.now()).strftime("%d %b %Y, %H:%M"),
        "user": request.user,
    }
    return render_pdf_response(
        "reports/pdf/grant_utilization_pdf.html",
        context,
        filename="grant_utilization_report.pdf",
        request=request,
    )


@login_required
@report_required
def financial_summary_pdf(request):
    total_grants = Grant.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    total_expenses = Expense.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    net_unspent = total_grants - total_expenses
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    context = {
        "total_grants": total_grants,
        "total_expenses": total_expenses,
        "net_unspent": net_unspent,
        "grants": grants,
        "generated_on": localtime(timezone.now()).strftime("%d %b %Y, %H:%M"),
        "user": request.user,
    }
    return render_pdf_response(
        "reports/pdf/financial_summary_pdf.html",
        context,
        filename="financial_summary_report.pdf",
        request=request,
    )


@login_required
@report_required
def compliance_status_pdf(request):
    docs = ComplianceDocument.objects.all()
    context = {
        "docs": docs,
        "generated_on": localtime(timezone.now()).strftime("%d %b %Y, %H:%M"),
        "user": request.user,
    }
    return render_pdf_response(
        "reports/pdf/compliance_status_pdf.html",
        context,
        filename="compliance_status_report.pdf",
        request=request,
    )


@login_required
@report_required
def expense_ledger_pdf(request):
    expenses = Expense.objects.filter(is_active=True).select_related("created_by").prefetch_related(
        "allocations__grant__donor"
    ).order_by("expense_date")
    grant_filter = request.GET.get("grant", "")
    if grant_filter:
        expenses = expenses.filter(allocations__grant_id=grant_filter).distinct()
    grant_name = ""
    if grant_filter:
        try:
            grant_name = Grant.objects.get(pk=grant_filter).name
        except Grant.DoesNotExist:
            pass
    expenses = list(expenses)
    total_amount = sum(e.total_amount for e in expenses)
    context = {
        "expenses": expenses,
        "grant_filter": grant_filter,
        "grant_name": grant_name,
        "total_amount": total_amount,
        "generated_on": localtime(timezone.now()).strftime("%d %b %Y, %H:%M"),
        "user": request.user,
    }
    return render_pdf_response(
        "reports/pdf/expense_ledger_pdf.html",
        context,
        filename="expense_ledger_report.pdf",
        request=request,
    )
