from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    """
    Restrict view to users whose role is in the given list.

    This is the primary role-based access control (RBAC) decorator used across
    PaperTrail. It ensures that only users with specific roles can access
    protected views. When access is denied, the user is redirected to the
    dashboard with an error message.

    Args:
        *roles: Variable number of role strings (e.g., "admin", "finance", "auditor")

    Returns:
        A decorator function that wraps the view.

    Example:
        @login_required
        @role_required("admin", "finance")
        def sensitive_view(request):
            # Only accessible to admin and finance roles
            pass

    Notes:
        - Must be stacked AFTER @login_required to ensure user is authenticated
        - Checks user.role attribute from custom User model
        - Logs error message via Django messages framework
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            # Check if user's role is in the allowed roles list
            if request.user.role not in roles:
                messages.error(request, "You do not have permission to access this page.")
                return redirect("accounts:dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def write_required(view_func):
    """
    Restrict view to Finance Manager (user.can_write == True) only.

    This decorator ensures that only users with role "finance" (Finance Manager)
    can access write/modify operations like creating or updating records.

    Args:
        view_func: The view function to decorate

    Returns:
        The wrapped view function

    Example:
        @login_required
        @write_required
        def expense_create(request):
            # Only Finance Manager can create expenses
            pass

    Notes:
        - Must be stacked AFTER @login_required
        - Checks user.can_write property, which is True only for Finance role
        - Redirects to dashboard with error message on access denial
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Verify user has write permissions (Finance Manager role)
        if not request.user.can_write:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("accounts:dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped


def finance_required(view_func):
    """
    Restrict view to Finance Manager users only.

    Functionally equivalent to @role_required("finance"), this specialized
    decorator is used when only the Finance Manager role is allowed to access
    a specific view or resource.

    Args:
        view_func: The view function to decorate

    Returns:
        The wrapped view function

    Example:
        @login_required
        @finance_required
        def grant_create(request):
            # Only Finance Manager can create grants
            pass

    Notes:
        - Must be stacked AFTER @login_required
        - Redirects to dashboard if user is not Finance Manager
        - Can be replaced with @role_required("finance") if preferred
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Verify user has finance role (exclusive)
        if request.user.role != "finance":
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("accounts:dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped


def report_required(view_func):
    """
    Restrict reports to Finance Manager and Auditor roles only.

    This decorator ensures that sensitive financial and audit reports are only
    accessible to users who have the appropriate permissions to review
    organizational financial and compliance data.

    Args:
        view_func: The view function to decorate

    Returns:
        The wrapped view function

    Example:
        @login_required
        @report_required
        def financial_summary_report(request):
            # Only Finance Manager and Auditor can view reports
            pass

    Notes:
        - Must be stacked AFTER @login_required
        - Allows access to both "finance" and "auditor" roles
        - Redirects to dashboard if user is Admin role
        - Used for all report views in the reports app
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Allow Finance Manager and Auditor to access reports
        if request.user.role not in ("finance", "auditor"):
            messages.error(request, "You do not have permission to access reports.")
            return redirect("accounts:dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped
