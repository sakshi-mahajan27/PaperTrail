from django.contrib import admin
from .models import Donor


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ["name", "donor_type", "email", "country", "is_active", "created_at"]
    list_filter = ["donor_type", "is_active", "country"]
    search_fields = ["name", "email", "pan_number"]
