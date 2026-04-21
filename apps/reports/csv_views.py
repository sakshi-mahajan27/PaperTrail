"""
CSV export views for PaperTrail reports.

Each view mirrors its corresponding HTML report view but returns an
HttpResponse with Content-Type: text/csv and a Content-Disposition
header so the browser prompts a file download.

Pattern:
    1. Reuse the same queryset as the HTML view.
    2. Write header row + data rows via Python's csv module.
    3. Return the response — no template needed.

URL routing:
    /reports/donor-expenses/csv/       → donor_expense_csv
    /reports/grant-utilization/csv/    → grant_utilization_csv
    /reports/financial-summary/csv/    → financial_summary_csv
    /reports/compliance-status/csv/    → compliance_status_csv
    /reports/expense-ledger/csv/       → expense_ledger_csv

Query parameter support:
    expense_ledger_csv honours ?grant=<id> (same as the HTML ledger view).

Authentication:
    All views require @login_required + @report_required (Finance Manager /
    Auditor roles only), matching the HTML report views.
"""

import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.decorators import report_required
from apps.compliance.models import ComplianceDocument
from apps.donors.models import Donor
from apps.expenses.models import Expense, ExpenseAllocation
from apps.grants.models import Grant


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _csv_response(filename: str) -> HttpResponse:
    """
    Return an HttpResponse pre-configured for CSV download.

    A UTF-8 BOM (\ufeff) is written as the very first byte so that Microsoft
    Excel auto-detects the encoding and does not garble non-ASCII characters
    (e.g. Indian donor names, rupee amounts with decimals, em dashes).

    Args:
        filename: The suggested download filename (e.g. 'grant_utilization.csv').

    Returns:
        HttpResponse with Content-Type text/csv, BOM pre-written, and
        Content-Disposition set so the browser triggers a file download.
    """
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # UTF-8 BOM — tells Excel to use UTF-8
    return response


# ---------------------------------------------------------------------------
# 1. Donor-wise Expense CSV
# ---------------------------------------------------------------------------

@login_required
@report_required
def donor_expense_csv(request):
    """
    Export donor-wise expense totals as a CSV file.

    Columns:
        #, Donor Name, Donor Type, PAN Number, Total Expenses (Rs.)

    Mirrors:
        reports.views.donor_expense_report  (HTML view)
        reports.pdf_views.donor_expense_pdf (PDF view)

    Query logic:
        For each active donor, sum all ExpenseAllocation.allocated_amount
        where the allocation's grant belongs to that donor and the expense
        is still active (is_active=True).

    Filename:
        donor_expense_report_<YYYY-MM-DD>.csv
    """
    today = timezone.localdate().isoformat()
    response = _csv_response(f"donor_expense_report_{today}.csv")
    writer = csv.writer(response)

    # Header
    writer.writerow(["#", "Donor Name", "Donor Type", "PAN Number", "Total Expenses (Rs.)"])

    donors = Donor.objects.filter(is_active=True).prefetch_related(
        "grants__allocations__expense"
    )
    grand_total = 0
    for i, donor in enumerate(donors, start=1):
        total = (
            ExpenseAllocation.objects.filter(
                grant__donor=donor, expense__is_active=True
            ).aggregate(t=Sum("allocated_amount"))["t"]
            or 0
        )
        grand_total += total
        writer.writerow([
            i,
            donor.name,
            donor.get_donor_type_display(),
            donor.pan_number or "N/A",
            f"{total:.2f}",
        ])

    # Grand total footer row
    writer.writerow(["", "", "", "Grand Total", f"{grand_total:.2f}"])
    writer.writerow(["", "", "", "Generated on", timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")])

    return response


# ---------------------------------------------------------------------------
# 2. Grant Utilization CSV
# ---------------------------------------------------------------------------

@login_required
@report_required
def grant_utilization_csv(request):
    """
    Export grant budget vs utilization data as a CSV file.

    Columns:
        #, Grant Name, Donor, Status, Start Date, End Date,
        Budget (Rs.), Utilized (Rs.), Remaining (Rs.), Burn Rate (%)

    Mirrors:
        reports.views.grant_utilization_report  (HTML view)
        reports.pdf_views.grant_utilization_pdf (PDF view)

    Filename:
        grant_utilization_report_<YYYY-MM-DD>.csv
    """
    today = timezone.localdate().isoformat()
    response = _csv_response(f"grant_utilization_report_{today}.csv")
    writer = csv.writer(response)

    writer.writerow([
        "#", "Grant Name", "Donor", "Status",
        "Start Date", "End Date",
        "Budget (Rs.)", "Utilized (Rs.)", "Remaining (Rs.)", "Burn Rate (%)",
    ])

    grants = Grant.objects.filter(is_active=True).select_related("donor")
    for i, grant in enumerate(grants, start=1):
        writer.writerow([
            i,
            grant.name,
            grant.donor.name,
            grant.get_status_display(),
            grant.start_date.isoformat(),
            grant.end_date.isoformat(),
            f"{grant.total_amount:.2f}",
            f"{grant.utilized_amount:.2f}",
            f"{grant.remaining_amount:.2f}",
            f"{grant.burn_rate:.1f}",
        ])

    writer.writerow(["", "", "", "", "", "", "", "", "Generated on",
                     timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")])

    return response


# ---------------------------------------------------------------------------
# 3. Financial Summary CSV
# ---------------------------------------------------------------------------

@login_required
@report_required
def financial_summary_csv(request):
    """
    Export the high-level financial summary as a CSV file.

    Structure:
        Section 1 — Aggregate metrics (total grants, expenses, unspent)
        Section 2 — Grant-wise breakdown table

    Mirrors:
        reports.views.financial_summary_report  (HTML view)
        reports.pdf_views.financial_summary_pdf (PDF view)

    Filename:
        financial_summary_report_<YYYY-MM-DD>.csv
    """
    today = timezone.localdate().isoformat()
    response = _csv_response(f"financial_summary_report_{today}.csv")
    writer = csv.writer(response)

    total_grants = (
        Grant.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    )
    total_expenses = (
        Expense.objects.filter(is_active=True).aggregate(t=Sum("total_amount"))["t"] or 0
    )
    net_unspent = total_grants - total_expenses

    # --- Summary block ---
    writer.writerow(["Financial Summary Report"])
    writer.writerow(["Generated on", timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")])
    writer.writerow([])
    writer.writerow(["Metric", "Amount (Rs.)"])
    writer.writerow(["Total Grants Awarded", f"{total_grants:.2f}"])
    writer.writerow(["Total Expenses Recorded", f"{total_expenses:.2f}"])
    writer.writerow(["Net Unspent Budget", f"{net_unspent:.2f}"])
    if total_grants:
        utilization_rate = round((total_expenses / total_grants) * 100, 1)
        writer.writerow(["Overall Utilization Rate (%)", f"{utilization_rate}"])
    writer.writerow([])

    # --- Grant-wise breakdown ---
    writer.writerow(["Grant Name", "Donor", "Status", "Budget (Rs.)", "Utilized (Rs.)", "Remaining (Rs.)"])
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    for grant in grants:
        writer.writerow([
            grant.name,
            grant.donor.name,
            grant.get_status_display(),
            f"{grant.total_amount:.2f}",
            f"{grant.utilized_amount:.2f}",
            f"{grant.remaining_amount:.2f}",
        ])

    return response


# ---------------------------------------------------------------------------
# 4. Compliance Status CSV
# ---------------------------------------------------------------------------

@login_required
@report_required
def compliance_status_csv(request):
    """
    Export compliance certificate status as a CSV file.

    Columns:
        Certificate Type, Issue Date, Expiry Date, Days to Expiry, Status, Status Label

    Mirrors:
        reports.views.compliance_status_report  (HTML view)
        reports.pdf_views.compliance_status_pdf (PDF view)

    Filename:
        compliance_status_report_<YYYY-MM-DD>.csv
    """
    today = timezone.localdate().isoformat()
    response = _csv_response(f"compliance_status_report_{today}.csv")
    writer = csv.writer(response)

    writer.writerow([
        "Certificate Type", "Issue Date", "Expiry Date",
        "Days to Expiry", "Status", "Status Label",
    ])

    for doc in ComplianceDocument.objects.all():
        days = doc.days_to_expiry
        days_display = f"Expired {abs(days)} days ago" if days < 0 else str(days)
        writer.writerow([
            doc.get_cert_type_display(),
            doc.issue_date.isoformat(),
            doc.expiry_date.isoformat(),
            days_display,
            doc.status.upper(),
            doc.status_label,
        ])

    writer.writerow([])
    writer.writerow(["Generated on", timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")])

    return response


# ---------------------------------------------------------------------------
# 5. Expense Ledger CSV
# ---------------------------------------------------------------------------

@login_required
@report_required
def expense_ledger_csv(request):
    """
    Export the expense ledger as a CSV file.

    Supports optional ?grant=<id> query parameter to filter by grant,
    matching the behaviour of the HTML expense ledger view.

    Columns:
        #, Date, Title, Total Amount (Rs.), Grant Allocations, Recorded By, Created At

    The 'Grant Allocations' column is a semicolon-separated list of
    "Grant Name (Rs. amount)" strings — one per allocation row —
    so all allocation data is preserved in a single cell without
    requiring Excel pivot tables.

    Mirrors:
        reports.views.expense_ledger_report  (HTML view)
        reports.pdf_views.expense_ledger_pdf (PDF view)

    Query parameters:
        grant (optional): Filter expenses by grant ID (?grant=3)

    Filename:
        expense_ledger_report_<YYYY-MM-DD>.csv
        expense_ledger_report_<grant_name>_<YYYY-MM-DD>.csv  (if filtered)
    """
    grant_filter = request.GET.get("grant", "")
    today = timezone.localdate().isoformat()

    expenses = (
        Expense.objects.filter(is_active=True)
        .select_related("created_by")
        .prefetch_related("allocations__grant__donor")
        .order_by("expense_date")
    )

    # Resolve optional grant filter
    grant_name = ""
    if grant_filter:
        expenses = expenses.filter(allocations__grant_id=grant_filter).distinct()
        try:
            grant_name = Grant.objects.get(pk=grant_filter).name
        except Grant.DoesNotExist:
            pass

    # Build filename
    safe_grant = grant_name.replace(" ", "_")[:40] if grant_name else ""
    filename_parts = ["expense_ledger_report"]
    if safe_grant:
        filename_parts.append(safe_grant)
    filename_parts.append(today)
    filename = "_".join(filename_parts) + ".csv"

    response = _csv_response(filename)
    writer = csv.writer(response)

    # Optional filter info header
    if grant_name:
        writer.writerow(["Filtered by Grant:", grant_name])
        writer.writerow([])

    writer.writerow([
        "#", "Date", "Title", "Total Amount (Rs.)",
        "Grant Allocations", "Recorded By", "Created At",
    ])

    expenses = list(expenses)
    total_amount = sum(e.total_amount for e in expenses)

    for i, expense in enumerate(expenses, start=1):
        allocations_str = "; ".join(
            f"{alloc.grant.name} (Rs.{alloc.allocated_amount:.2f})"
            for alloc in expense.allocations.all()
        )
        writer.writerow([
            i,
            expense.expense_date.isoformat(),
            expense.title,
            f"{expense.total_amount:.2f}",
            allocations_str,
            expense.created_by.username,
            expense.created_at.strftime("%Y-%m-%d %H:%M"),
        ])

    # Footer totals
    writer.writerow(["", "", "TOTAL", f"{total_amount:.2f}", "", "", ""])
    writer.writerow([])
    writer.writerow(["Generated on", timezone.now().strftime("%Y-%m-%d %H:%M")])

    return response
