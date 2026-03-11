from django.contrib import admin
from .models import ComplianceDocument


@admin.register(ComplianceDocument)
class ComplianceDocumentAdmin(admin.ModelAdmin):
    list_display = ["cert_type", "issue_date", "expiry_date", "status", "uploaded_by"]
    readonly_fields = ["uploaded_at", "updated_at", "uploaded_by"]
