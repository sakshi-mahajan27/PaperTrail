from django.contrib import admin
from .models import Expense, ExpenseAllocation


class AllocationInline(admin.TabularInline):
    """
    Inline editing for ExpenseAllocation within the Expense admin.

    Allows admins to create/edit allocations directly while editing the parent
    Expense. Displayed as a table where each row is one allocation (grant + amount).

    Features:
        extra = 1: Always shows one blank row for quick new allocation entry
        model = ExpenseAllocation: Links to the through table
        Tabular layout: Better UX for many allocations per expense

    UI Usage:
        1. Admin opens an Expense edit page
        2. Sees "Allocations" section at bottom with table
        3. Can edit existing allocations or add new row
        4. Changes sync when admin clicks Save

    Displayed Columns:
        - expense: Read-only (parent expense being edited)
        - grant: Dropdown to select grant
        - allocated_amount: Decimal input

    Query Optimization:
        Django automatically fetches related grants (prefetch_related).
        No extra queries beyond the base Expense + related Allocations.

    Validation:
        Note: No validation here—FormSet validation happens in views.py.
        Admin can enter invalid data (e.g., allocations summing to wrong total).
        This is intentional—views.py has proper validation.

    Notes:
        - Read-only fields: None (all editable)
        - Extra blank rows added for convenience
        - For bulk allocation edits, use ExpenseAllocationAdmin directly
    """
    model = ExpenseAllocation
    extra = 1


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    """
    Django admin interface for Expense records.

    Allows admins to view, search, and filter all expenses. Edit/delete disabled
    to prevent accidental data loss—finance staff use the web forms instead.

    List Display (Columns):
        - title: Expense description (clickable to view/edit)
        - total_amount: Total expense amount in ₹ currency
        - expense_date: Date expense was incurred
        - created_by: User who recorded expense (FK to User)
        - is_active: Soft-delete status (True = active, False = archived)

    List Filters (Right Sidebar):
        - is_active: Show active/archived/all expenses
        - expense_date: Filter by date range

    Search (Top Search Box):
        - title: Keyword search on expense title/description

    Inlines (Nested Editing):
        - AllocationInline: Edit allocations below expense details

    Permissions:
        - Edit: Allowed (but encourage use of web form instead)
        - Delete: Allowed (but see notes about soft-delete)
        - Add: Allowed (but encourage use of web form instead)

    Why Admin vs Web Form?
        - Web form: ExpenseForm with compliance gate checks
        - Admin: Direct DB access, no validation
        - Recommendation: Use web form for normal data entry

    Business Logic Notes:
        - Soft-delete (is_active): Never actually delete expenses
        - If a mistake: Set is_active=False instead
        - Deleting breaks audit trail and budget calculations
        - All expenses preserved for compliance audits

    Performance Considerations:
        - list_display includes FK (created_by) → auto select_related applied
        - inlines expands allocations → auto prefetch_related applied
        - No pagination shown—use list_filter to reduce results

    Query Example:
        Admin opens expense list:
        1. Fetch all Expense with is_active filter applied
        2. select_related("created_by") to fetch user names  
        3. For each expense, fetch related ExpenseAllocation + Grant
        Typical: ~1 query for expenses + 1 for users + 1 for allocations

    Common Admin Tasks:
        - View: Click title to see full details
        - Filter: Use is_active to hide archived expenses
        - Search: Type in title to find by keyword
        - Edit: Change title, date, or allocations
        - Archive: Change is_active to False (soft delete)

    Audit Trail Impact:
        - All admin edits logged by AuditLog signals
        - Shows what changed, who changed it, when
        - Tracked fields: title, total_amount, expense_date, is_active
    """
    list_display = ["title", "total_amount", "expense_date", "created_by", "is_active"]
    list_filter = ["is_active", "expense_date"]
    search_fields = ["title"]
    inlines = [AllocationInline]


@admin.register(ExpenseAllocation)
class ExpenseAllocationAdmin(admin.ModelAdmin):
    """
    Django admin interface for ExpenseAllocation records (direct access).

    Allows admins to view, search, and filter expense allocations. Useful for
    bulk changes or viewing all allocations across all expenses.

    List Display (Columns):
        - expense: FK to Expense (expense title)
        - grant: FK to Grant (grant name)
        - allocated_amount: Amount allocated to this grant (₹)

    Typical Usage:
        - View all allocations across all expenses
        - Filter by grant to see total spending per grant
        - Advanced: Generate reports of grant spending
        - Troubleshoot: Find which expenses allocated to which grants

    Why Both expenseAllocationAdmin + Inline?
        - Inline (in ExpenseAdmin): For editing during expense management
        - Direct admin: For bulk viewing/analysis of allocations only

    Business Meaning:
        Each row represents "Expense X contributed ₹Y to Grant Z".
        Together, these rows split the expense across multiple donors' grants.

    Constraints:
        - Unique constraint: (expense, grant) - can't allocate same expense
          to same grant twice
        - This prevents duplicates but allows reallocation (edit amount)
        - Soft-delete: Honors expense.is_active (shows only from active expenses)

    No Inlines:
        - ExpenseAllocation is already a "through table"
        - No deeper nesting allowed (keeps UI clean)

    Audit Impact:
        - Admin edits to allocated_amount trigger AuditLog
        - Shows: Old amount vs new amount, who changed it, when
    """
    list_display = ["expense", "grant", "allocated_amount"]
