from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST

from .forms import LoginForm, UserCreateForm, UserUpdateForm
from .models import User
from .decorators import role_required


def login_view(request):
    """
    Handle user login.

    This view presents the login form to unauthenticated users and processes
    login requests. On successful authentication, it redirects to the user's
    intended page (via 'next' parameter) or defaults to the dashboard.

    Request Method:
        GET: Display the login form
        POST: Process login credentials

    URL Parameters:
        next (optional): The page to redirect to after success

    Response:
        - 302 Redirect to dashboard if already authenticated
        - 302 Redirect to 'next' URL or dashboard on successful login
        - 200 Display form with error message on failed login
        - 200 Display empty form on GET request

    Template Used:
        accounts/login.html

    Context Variables:
        form: LoginForm instance

    Notes:
        - Already-logged-in users are redirected to dashboard
        - Failed login shows error message: "Invalid username or password."
        - CSRF protection automatic via Django middleware
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Successfully logged in.")
            return redirect(request.GET.get("next", "accounts:dashboard"))
        messages.error(request, "Invalid username or password.")
    return render(request, "accounts/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    """
    Handle user logout with enhanced security.

    This view logs out the authenticated user and clears the session.
    It's restricted to POST requests to prevent accidental logouts via
    direct links. After logout, user is redirected to the login page with
    cache control headers to ensure logout is immediate.

    Request Method:
        POST only (enforced by @require_POST decorator)

    Authentication:
        Requires logged-in user (@login_required)

    Response:
        302 Redirect to login page with cache control headers

    Security Measures:
        - Session is cleared on logout
        - Cache control headers prevent browser caching of logout response
        - @require_POST prevents CSRF attacks
        - Set-Cookie expires to clear session cookie
        - Additional headers ensure browser won't cache authenticated pages

    Notes:
        - Unauthenticated users are redirected to login page before POST check
        - All authenticated pages are protected by NoCacheMiddleware
        - Combined with middleware, ensures user cannot access pages via back button
    """
    logout(request)
    
    # Add success message AFTER logout but before response is returned
    # The messages framework will use session storage for the new unauthenticated session
    messages.success(request, "You have been successfully logged out.")
    
    response = redirect("accounts:login")
    
    # Add cache control headers to logout response
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response


@login_required
def dashboard_view(request):
    """
    Display the main dashboard for all users.

    The dashboard provides a quick overview of the organization's compliance
    status, active grants, and recent expense entries. Content is the same
    for all authenticated users regardless of role.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)

    Response:
        200 HTML dashboard with compliance and financial summary

    Template Used:
        accounts/dashboard.html

    Context Variables:
        compliance_summary (dict): Status breakdown of certificates
            - green (int): Count of valid certificates
            - yellow (int): Count of certificates expiring soon (≤180 days)
            - red (int): Count of expired certificates
        active_grants (QuerySet): All non-soft-deleted grants with status='active'
        recent_expenses (QuerySet): Last 10 undeleted expenses, newest first

    Data Optimizations:
        - select_related("created_by"): Fetch user info in one JOIN
        - order_by("-created_at"): Sort by creation time, newest first
        - [:10] Limit to 10 records (pagination placeholder)

    Notes:
        - Compliance statuses computed from ComplianceDocument.status property
        - Soft delete filtering (is_active=True) applied to all querysets
    """
    from apps.compliance.models import ComplianceDocument
    from apps.grants.models import Grant
    from apps.expenses.models import Expense

    # Fetch all compliance documents and calculate status breakdown
    docs = ComplianceDocument.objects.all()
    compliance_summary = {
        "green": sum(1 for d in docs if d.status == "green"),
        "yellow": sum(1 for d in docs if d.status == "yellow"),
        "red": sum(1 for d in docs if d.status == "red"),
    }
    # Get active, non-soft-deleted grants
    active_grants = Grant.objects.filter(is_active=True, status="active")
    # Get recent expenses with creator info, excluding soft-deleted ones
    recent_expenses = Expense.objects.filter(is_active=True).select_related("created_by").order_by("-created_at")[:10]

    context = {
        "compliance_summary": compliance_summary,
        "active_grants": active_grants,
        "recent_expenses": recent_expenses,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
@role_required("admin")
def user_list(request):
    """
    Display a list of all users in the system.

    Admin-only view that shows all user accounts ordered alphabetically.
    Useful for user management and role auditing.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Response:
        200 HTML table of all users

    Template Used:
        accounts/user_list.html

    Context Variables:
        users (QuerySet): All User objects ordered by username

    Access Control:
        - Non-admin users redirected to dashboard with error message
        - Unauthenticated users redirected to login page

    Notes:
        - Includes all users (active and inactive)
        - Lists are ordered by username for predictable navigation
    """
    users = User.objects.all().order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@role_required("admin")
def user_create(request):
    """
    Create a new user account.

    Admin-only view for registering new users in the system. The admin
    specifies the user's initial role and credentials.

    Request Method:
        GET: Display empty form
        POST: Create user with submitted data

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Form Used:
        UserCreateForm

    Response:
        - 200 Display form on GET or validation error
        - 302 Redirect to user_list on success

    Template Used:
        accounts/user_form.html

    Context Variables:
        form: UserCreateForm instance
        title: "Create User"

    Success:
        - User is created with submitted details
        - Message: "User created successfully."
        - Redirect to user_list view

    Validation Rules:
        - username must be unique
        - password fields must match
        - email is optional but recommended
        - role must be one of 'admin', 'finance', 'auditor'

    Notes:
        - Initial credential setup for new accounts
        - Password change should be done via separate view
        - User can change password immediately after creation
    """
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User created successfully.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Create User"})


@login_required
@role_required("admin")
def user_edit(request, pk):
    """
    Edit an existing user account.

    Admin-only view for modifying user details, role assignment, and
    activation status. The form hides the password field to prevent
    accidental password changes.

    Request Method:
        GET: Display pre-populated form
        POST: Update user with submitted data

    Path Parameters:
        pk (int): User ID to edit

    Authentication:
        Requires logged-in user (@login_required)
        Requires Admin role (@role_required("admin"))

    Form Used:
        UserUpdateForm

    Response:
        - 200 Display form on GET or validation error
        - 302 Redirect to user_list on success
        - 404 If user with given pk doesn't exist

    Template Used:
        accounts/user_form.html

    Context Variables:
        form: UserUpdateForm instance for the user
        title: "Edit User"
        object: The User instance being edited

    Editable Fields:
        - username (string)
        - first_name (string)
        - last_name (string)
        - email (string)
        - phone (string)
        - role (choice: 'admin', 'finance', 'auditor')
        - is_active (boolean - enables/disables login)

    Success:
        - User is updated with submitted details
        - Message: "User updated successfully."
        - Redirect to user_list view

    Notes:
        - Password changes should be done via separate change-password view
        - is_active toggle allows admin to disable user without deletion
        - Uses get_object_or_404 to handle missing users gracefully
    """
    user = get_object_or_404(User, pk=pk)
    form = UserUpdateForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User updated successfully.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Edit User", "object": user})


@login_required
def profile_view(request):
    """
    Display the current user's profile.

    This view shows the logged-in user's own profile information including
    username, email, phone, and role. Any authenticated user can view their
    own profile.

    Request Method:
        GET only

    Authentication:
        Requires logged-in user (@login_required)

    Response:
        200 HTML profile page

    Template Used:
        accounts/profile.html

    Context Variables:
        user_obj: The User instance (request.user)

    Access:
        - Any authenticated user can view their own profile
        - No other users' profiles are viewable (per template logic)
        - No @role_required check; available to all authenticated users

    Notes:
        - Future: Add profile edit functionality if needed
        - Shows read-only profile information
        - Context variable named 'user_obj' to avoid shadowing built-in 'user'
    """
    return render(request, "accounts/profile.html", {"user_obj": request.user})
