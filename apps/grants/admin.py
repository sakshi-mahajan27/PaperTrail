from django.contrib import admin
from .models import Grant


@admin.register(Grant)
class GrantAdmin(admin.ModelAdmin):
    list_display = ["name", "donor", "total_amount", "start_date", "end_date", "status", "is_active"]
    list_filter = ["status", "is_active"]
    search_fields = ["name", "donor__name"]
