from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Donor
from .forms import DonorForm
from apps.accounts.decorators import role_required, finance_required


@login_required
@role_required("admin", "finance", "auditor")
def donor_list(request):
    """
    Display a list of all active donors with search and filter options.

    This view shows all active donors in the system with search by name
    and filtering by donor type. Both Finance Managers and Auditors can view.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Query Parameters:
        q (optional): Search term for donor name
            Case-insensitive substring match (name__icontains)
            Example: /donors/?q=Save
        
        type (optional): Filter by donor type
            One of 'individual', 'organization', 'government', 'corporate'
            Example: /donors/?type=corporate

    Response:
        200 HTML table of donors matching search/filter

    Template Used:
        donors/donor_list.html

    Context Variables:
        donors (QuerySet): Filtered list of active donors
        search_q (str): The search query (if any)
        type_filter (str): The type filter (if any)
        type_choices (list): All available donor types (for filter dropdown)

    Data Filtering:
        - Base query: Donor.objects.filter(is_active=True)
        - If q parameter: Also filter by name__icontains=q
        - If type parameter: Also filter by donor_type=type
        - Results ordered alphabetically by name

    Performance:
        - No select_related or prefetch needed (simple model)
        - Small dataset (typically < 50 donors)
        - Indexed by created_at for queryability

    Implementation:
        1. Get base queryset (active donors only)
        2. If q in GET: filter by name
        3. If type in GET: filter by donor_type
        4. Render with context including original filters

    Notes:
        - Soft-deleted donors (is_active=False) never shown
        - Search is case-insensitive (user-friendly)
        - Filter dropdown shows all 4 types regardless of data
        - Used to build grant donor relationships
    """
    qs = Donor.objects.filter(is_active=True)
    q = request.GET.get("q", "").strip()
    dtype = request.GET.get("type", "")
    if q:
        qs = qs.filter(name__icontains=q)
    if dtype:
        qs = qs.filter(donor_type=dtype)
    return render(request, "donors/donor_list.html", {
        "donors": qs,
        "search_q": q,
        "type_filter": dtype,
        "type_choices": Donor.TYPE_CHOICES,
    })


@login_required
@role_required("admin", "finance", "auditor")
def donor_detail(request, pk):
    """
    Display detailed view of a single donor.

    Shows all donor information including contact details, donor type,
    and related grants.

    Request Method:
        GET only

    Path Parameters:
        pk (int): Primary key of Donor to display

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin, Finance, or Auditor role

    Response:
        - 200 HTML detail page
        - 404 If donor doesn't exist or is inactive (is_active=False)

    Template Used:
        donors/donor_detail.html

    Context Variables:
        donor: The Donor instance

    Displayed Information:
        - Donor name and type
        - Contact email and phone
        - Country and address
        - PAN number (if available)
        - Internal notes
        - List of related grants
        - Created/updated timestamps

    Links/Actions Available:
        - Edit donor (admin/finance only)
        - Deactivate donor (soft delete)
        - View related grants
        - Back to donor list

    Notes:
        - Uses get_object_or_404 to handle missing records
        - Only active donors are accessible (is_active check in queryset)
        - Template shows related grants for context
    """
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    return render(request, "donors/donor_detail.html", {"donor": donor})


@login_required
@finance_required
def donor_create(request):
    """
    Create a new donor record.

    Finance Manager and Admin users can register new donors in the system.
    This is the entry point for adding funding sources to the grant registry.

    Request Method:
        GET: Display empty form
        POST: Create donor with submitted data

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Form Used:
        DonorForm

    Response:
        - 200 Display form on GET
        - 302 Redirect to donor_list on success
        - 200 Display form with validation errors on POST failure

    Template Used:
        donors/donor_form.html

    Context Variables:
        form: DonorForm instance (empty on GET)
        title: "Register Donor"

    Form Fields:
        - name: Donor name (required)
        - donor_type: Individual/Org/Govt/Corporate
        - email: Contact email (optional)
        - phone: Contact phone (optional)
        - country: Default 'India' (optional)
        - address: Mailing address (optional)
        - pan_number: PAN for Indian tax (optional)
        - notes: Internal notes (optional)

    Success Flow:
        1. Finance Manager fills donor form
        2. Submits POST
        3. Form validated
        4. Donor created (is_active=True by default)
        5. Message: "Donor registered successfully."
        6. Redirect to donor_list
        7. Audit log created (signals.py)

    Use Case:
        Finance Manager contacts "Save the Children" and negotiates $100,000 grant.
        1. Creates donor record with their details
        2. Can now create grants linked to this donor

    Notes:
        - is_active=True by default (no explicit setting needed)
        - Audit trail created via post_save signal
        - No email verification or contact check
        - PAN number validated only by length (optional check)
    """
    form = DonorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Donor registered successfully.")
        return redirect("donors:donor_list")
    return render(request, "donors/donor_form.html", {"form": form, "title": "Register Donor"})


@login_required
@finance_required
def donor_edit(request, pk):
    """
    Edit an existing donor record.

    Finance Manager can update donor details like contact info, type, or notes.

    Request Method:
        GET: Display for-populated form
        POST: Update donor with submitted data

    Path Parameters:
        pk (int): Primary key of Donor to edit

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Form Used:
        DonorForm

    Response:
        - 200 Display form on GET or error
        - 302 Redirect to donor_detail on success
        - 404 If donor doesn't exist or is inactive

    Template Used:
        donors/donor_form.html

    Context Variables:
        form: DonorForm instance, pre-filled with current data
        title: "Edit Donor"
        object: The Donor being edited

    Editable Fields:
        - name: Can rename donor
        - donor_type: Can reclassify
        - email, phone: Update contact
        - country, address: Update location
        - pan_number: Add or update PAN
        - notes: Update internal notes

    Preserved Fields:
        - is_active: Cannot be edited here (use separate delete view)
        - created_at: Never changes
        - updated_at: Auto-refreshed on save

    Success Flow:
        1. Finance Manager navigates to edit donor
        2. Form shows current values
        3. Updates contact or other info
        4. Submits POST
        5. Donor updated
        6. Message: "Donor updated successfully."
        7. Redirect to donor_detail
        8. Audit log created (what fields changed)

    Notes:
        - Uses get_object_or_404 to handle missing/inactive donors
        - updated_at field automatically refreshed (auto_now=True)
        - Audit trail shows what changed via AuditLog model
        - Cannot change is_active here (see donor_delete view)
    """
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    form = DonorForm(request.POST or None, instance=donor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Donor updated successfully.")
        return redirect("donors:donor_detail", pk=pk)
    return render(request, "donors/donor_form.html", {"form": form, "title": "Edit Donor", "object": donor})


@login_required
@finance_required
def donor_delete(request, pk):
    """
    Deactivate a donor (soft delete, not permanent deletion).

    Finance Manager can deactivate donors when a donor relationship ends.
    Uses soft-delete (is_active=False) to preserve historical data.

    Request Method:
        GET: Display confirmation page
        POST: Deactivate the donor

    Path Parameters:
        pk (int): Primary key of Donor to deactivate

    Authentication:
        Requires logged-in user (@login_required)
        Requires Finance Manager role (@finance_required)

    Response:
        - 200 Display confirmation page on GET
        - 302 Redirect to donor_list on confirmed POST
        - 404 If donor doesn't exist or already inactive

    Template Used:
        donors/donor_confirm_delete.html

    Context Variables:
        donor: The Donor being deactivated

    Deactivation (Soft Delete):
        1. Confirmation page asks for user confirmation
        2. On POST: donor.is_active = False
        3. Call donor.save()
        4. Message: "Donor '{name}' has been deactivated."
        5. Redirect to donor_list
        6. Audit log created (action=deleted)

    Data Preservation:
        - Original donor record preserved in database
        - Historical grants still linked to donor
        - If reactivating needed, uncomment/modify is_active in future
        - Soft delete allows auditing of deactivations

    Why Soft Delete?
        - Preserve historical grant/expense data
        - Enable audit trails
        - Allow "undo" if deactivation was mistake
        - Meet regulatory requirements for data retention

    Impact on Views:
        - donor_list filters is_active=True (deactivated donors hidden)
        - donor_detail filters is_active=True (404 if deactivated)
        - Reports can still include if needed (override filter)

    Notes:
        - Uses get_object_or_404 with is_active=True check
        - Message shown on successful deactivation
        - Requires POST for safety (not just GET link)
        - Related grants remain linked (no cascading changes)
    """
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    if request.method == "POST":
        donor.is_active = False
        donor.save()
        messages.success(request, f"Donor '{donor.name}' has been deactivated.")
        return redirect("donors:donor_list")
    return render(request, "donors/donor_confirm_delete.html", {"donor": donor})
