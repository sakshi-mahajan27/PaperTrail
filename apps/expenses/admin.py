from django.contrib import admin
from .models import Expense, ExpenseAllocation


class AllocationInline(admin.TabularInline):
    model = ExpenseAllocation
    extra = 1


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["title", "total_amount", "expense_date", "created_by", "is_active"]
    list_filter = ["is_active", "expense_date"]
    search_fields = ["title"]
    inlines = [AllocationInline]


@admin.register(ExpenseAllocation)
class ExpenseAllocationAdmin(admin.ModelAdmin):
    list_display = ["expense", "grant", "allocated_amount"]
