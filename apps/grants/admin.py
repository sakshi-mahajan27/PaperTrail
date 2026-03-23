from django.contrib import admin
from .models import Grant


@admin.register(Grant)
class GrantAdmin(admin.ModelAdmin):
    """
    Django admin interface for Grant records.

    Allows admins to view, search, and filter grants. Edit/delete available
    but web forms preferred for normal operations.

    List Display (Columns):
        - name: Grant name/title (clickable to view/edit)
        - donor: Donor who authorized this grant (FK to Donor)
        - total_amount: Total budget authorized (₹)
        - start_date: First spending date
        - end_date: Last spending date
        - status: Lifecycle status (pending/active/closed)
        - is_active: Soft-delete flag (True = active, False = archived)

    List Filters (Right Sidebar):
        - status: Filter by lifecycle status (pending/active/closed)
        - is_active: Show active/archived/all grants

    Search Fields:
        - name: Keyword search on grant title
        - donor__name: Search by donor organization name
            Uses __name to search related Donor object's name field

    Search Example:
        User types "Rural Education" → finds all grants with that title
        User types "Foundation" → finds all grants from donors containing "Foundation"

    Permissions:
        - Edit: Allowed (web form preferred)
        - Delete: Allowed (soft-delete recommended instead)
        - Add: Allowed (web form GrantForm preferred)

    Why Admin vs Web Form?
        - Web form (GrantForm): Compliance gate (is_compliant check), better validation
        - Admin: Direct DB access, no compliance checks
        - Recommendation: Use web form for normal operations

    When to Use Admin:
        - Bulk edits across multiple grants
        - Quick status changes
        - Emergency corrections
        - Admin oversight/audits

    Business Logic Notes:
        - Soft-delete (is_active): Never delete grants
          - Breaks allocation history
          - If mistake: Set is_active=False instead
        - Status transitions: PENDING → ACTIVE → CLOSED
          - PENDING: Just created, not yet spending
          - ACTIVE: Live, accepting allowance allocations
          - CLOSED: Grace, no new allocations
        - Compliance: Not re-checked in admin
          - Web form checks on create only

    Performance Considerations:
        - list_display with FK (donor) → auto select_related applied
        - search_fields with donor__name → auto join to Donor table
        - No inlines (Allocations managed separately via Expense)

    Query Example:
        Admin opens grant list:
        1. Fetch all Grant with filters applied
        2. select_related("donor") for name display
        3. Typical: ~1 query for grants

    Common Admin Tasks:
        - View: Click name to see full details
        - Filter: Use status/is_active to reduce results
        - Search: Search by title or donor name
        - Edit: Change any field (careful with budget/dates)
        - Archive: Set is_active=False (soft delete)
        - Delete: Actually delete record (see notes below)

    Delete Warning:
        Hard deleting a grant:
        - Orphans all allocations pointing to it
        - Breaks expense records (FK integrity)
        - Loses allocation history
        - NEVER hard delete—use soft delete (is_active=False)

    Audit Trail Impact:
        - All admin edits logged by signals
        - Shows what changed, who changed it, when
        - Tracked fields: name, donor, total_amount, status, is_active
        - Helpful for compliance audits

    Filter Combinations:
        - status="active" + is_active=True: Currently active grants
        - status="closed" + is_active=True: Finished grants
        - status="pending" + is_active=True: Not yet started grants
        - is_active=False: Archived/deleted grants (rarely viewed)

    Donor Column:
        Shows full donor name from FK.
        If donor is soft-deleted (is_active=False), still shown in grant
        (PROTECT on_delete prevents normal deletion).

    Related Views:
        - grant_list: All active grants, status filter, allocations shown
        - grant_detail: Full grant detail, expenses breakdown
        - grant_create: New grant with compliance check
        - grant_edit: Update grant
        - grant_close: Mark as closed
    """
    list_display = ["name", "donor", "total_amount", "start_date", "end_date", "status", "is_active"]
    list_filter = ["status", "is_active"]
    search_fields = ["name", "donor__name"]
