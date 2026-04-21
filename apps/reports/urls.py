from django.urls import path
from . import views, pdf_views, csv_views

app_name = "reports"

urlpatterns = [
    path("", views.report_index, name="report_index"),
    path("donor-expenses/", views.donor_expense_report, name="donor_expense"),
    path("grant-utilization/", views.grant_utilization_report, name="grant_utilization"),
    path("financial-summary/", views.financial_summary_report, name="financial_summary"),
    path("compliance-status/", views.compliance_status_report, name="compliance_status"),
    path("expense-ledger/", views.expense_ledger_report, name="expense_ledger"),
    # PDF exports
    path("donor-expenses/pdf/", pdf_views.donor_expense_pdf, name="donor_expense_pdf"),
    path("grant-utilization/pdf/", pdf_views.grant_utilization_pdf, name="grant_utilization_pdf"),
    path("financial-summary/pdf/", pdf_views.financial_summary_pdf, name="financial_summary_pdf"),
    path("compliance-status/pdf/", pdf_views.compliance_status_pdf, name="compliance_status_pdf"),
    path("expense-ledger/pdf/", pdf_views.expense_ledger_pdf, name="expense_ledger_pdf"),
    # CSV exports
    path("donor-expenses/csv/", csv_views.donor_expense_csv, name="donor_expense_csv"),
    path("grant-utilization/csv/", csv_views.grant_utilization_csv, name="grant_utilization_csv"),
    path("financial-summary/csv/", csv_views.financial_summary_csv, name="financial_summary_csv"),
    path("compliance-status/csv/", csv_views.compliance_status_csv, name="compliance_status_csv"),
    path("expense-ledger/csv/", csv_views.expense_ledger_csv, name="expense_ledger_csv"),
]

