from django.contrib import admin
from .models import Donor


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    """
    Django admin interface for Donor records.

    Allows admins to view, search, and filter donor organizations and individuals.
    Edit/delete available but web forms (DonorForm) preferred for normal operations.

    List Display (Columns):
        - name: Donor name/organization name (clickable to edit)
        - donor_type: Type (individual/organization/government/corporate)
        - email: Contact email address
        - country: Country of residence/registration
        - is_active: Soft-delete flag (True = active, False = archived)
        - created_at: When donor was first recorded

    List Filters (Right Sidebar):
        - donor_type: Filter by donor category
            Examples: "Individual", "Organization", "Government", "Corporate"
        - is_active: Show active/archived/all donors
        - country: Filter by country of origin

    Search Fields:
        - name: Keyword search on donor name
            Example: Type "Foundation" → finds all foundations
        - email: Search by email address
        - pan_number: Search by PAN (tax ID)
            PAN format: Only for individual/organization, 10-character code

    Editable Fields:
        - name: Donor name
        - donor_type: Category (individual/organization/government/corporate)
        - email: Contact email
        - phone: Contact phone
        - address: Physical address
        - country: Country
        - website: Organization website (if applicable)
        - pan_number: Tax ID (for individuals/organizations only)

    Business Logic:
        Donor Types:
        - individual: Person who donates
        - organization: NGO, foundation, company, etc.
        - government: Government department or ministry
        - corporate: Business/company donating

        PAN (Permanent Account Number):
        - India-specific tax identity
        - 10-character code (format: AAAAA0000A)
        - Used for tax compliance
        - Required for organizations (80G/12A benefits)

        Soft-Delete:
        - is_active=False: Donor archived (not deleted)
        - All grants/allocations preserved (FK integrity via PROTECT)
        - Views filter is_active=True (hidden from normal view)

    Permissions:
        - Edit: Allowed (but web form DonorForm preferred)
        - Delete: Prevented (PROTECT on_delete in Grant model)
          Can't delete if grants exist—must soft-delete instead
        - Add: Allowed (but web form preferred)

    Typical Admin Tasks:
        - View: Click name to see all details
        - Filter: Use donor_type to see only organizations
        - Search: Type email to find specific donor
        - Edit: Correct phone, address, or PAN
        - Archive: Set is_active=False (soft delete)
        - Create: Add new donor (usually via web form instead)

    Data Integrity:
        on_delete=PROTECT:
        - Can't delete donor if grants exist
        - Error shown: "Cannot delete, X grants reference this donor"
        - Must manually soft-delete (is_active=False) instead

    Audit Impact:
        Changes logged by signals:
        - name, donor_type, email, phone, address changes tracked
        - Shows: Old value → New value, who changed it, when
        - Helpful for accountability (prevents donor info loss)

    Filter Combinations:
        - donor_type="organization" + is_active=True: Active organizations
        - country="IN" + is_active=True: Active Indian donors
        - is_active=False: Archived donors (rarely needed)

    Query Performance:
        - list_display has no ForeignKeys (no N+1 issue)
        - search_fields are indexed (name, email, pan_number)
        - list_filter may slow if many donors (consider pagination)

    Related Model Impacts:
        Grant.donor (ForeignKey):
        - on_delete=PROTECT prevents hard deletion
        - If donor.pk deleted, all grants orphaned (error)
        - Soft-delete (is_active=False) recommended instead

    Related Views/Forms:
        - donor_list: Web view of all donors with search/filter
        - donor_detail: Donor profile with grants breakdown
        - donor_create: New donor form (with validation)
        - donor_edit: Update donor info
        - DonorForm: Web form (preferred over admin for consistency)

    Special Fields:

        PAN Number:
        - 10-character format for Indian tax ID
        - Example: ABCDE1234F
        - Field type: CharField (no auto-formatting)
        - Validation: None in model (could add regex)

        Website:
        - Optional URL field
        - For organizations/corporate
        - Not required

        Address:
        - Full address (street, city, state, country)
        - Optional text field

    Notes:
        - No inlines (Donor is simple model, grants edited separately)
        - Email not unique (can have duplicates—unusual but allowed)
        - Name not unique (can have multiple "John Smith"—risky but allowed)
        - Consider adding unique constraints in future
        - Consider adding email validation
    """
    list_display = ["name", "donor_type", "email", "country", "is_active", "created_at"]
    list_filter = ["donor_type", "is_active", "country"]
    search_fields = ["name", "email", "pan_number"]
