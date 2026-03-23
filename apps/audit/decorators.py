from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponseForbidden


def auditor_required(view_func):
    """
    Decorator to restrict view access to Auditor role only.

    This decorator enforces role-based access control for audit-related views.
    Auditors are the only role that can view audit logs and related audit data.

    Behavior:
        1. Check if user is authenticated (@login_required)
           - If not: Redirect to login page
        2. Check if user.is_auditor is True
           - If False: Return 403 Forbidden with error message
           - If True: Call the wrapped view function

    Role Hierarchy:
        - Admin: Full access (is_admin_role=True)
        - Finance Manager: Can create/edit grants & expenses (is_finance=True)
        - Auditor: Read-only access to audit trail (is_auditor=True)
        - User with no roles: Get 403 errors

    Usage:
        ```python
        @login_required
        @auditor_required
        def audit_log_list(request):
            '''Display audit logs to auditor only.'''
            return render(request, 'audit/audit_log_list.html', {...})
        ```

    Decorator Stack Order:
        - @login_required MUST be inner (closest to function)
        - @auditor_required MUST be outer
        - Example: @auditor_required decorator calls @login_required

    Error Responses:

        1. Not Authenticated:
           - Response: Redirect to login page
           - Status: 302 Redirect
           - Cause: User not logged in

        2. Not Auditor:
           - Response: 403 Forbidden
           - Message: "You do not have permission to access this page. Only auditors can view audit logs."
           - Status: 403
           - Cause: User logged in but is_auditor=False

        3. Success:
           - Response: Execute wrapped view function
           - Status: View's normal response
           - Cause: User authenticated AND is_auditor=True

    Related Role Checks:
        - @role_required ("admin", "auditor"): Accepts admin OR auditor
        - @auditor_required: Accepts auditor ONLY
        - @finance_required: Accepts finance manager ONLY

        Difference:
        - Use @role_required for views accessible to multiple roles
        - Use @auditor_required when ONLY auditors should see

    Views Using This Decorator:
        - audit_log_list: List all audit logs with search/filter
        - audit_log_detail: View specific audit log via AJAX
        - Any other audit-specific endpoints (future)

    User Model Integration:
        Checks request.user.is_auditor (@property from User model)
        User.is_auditor = (user.role == User.ROLE_AUDITOR)

    Implementation:
        - Uses functools.wraps to preserve wrapped function metadata
        - Returns HttpResponseForbidden (not redirect) for auth failures
        - This prevents redirect loops in protected areas

    See Also:
        - apps.accounts.decorators.role_required()
        - apps.accounts.models.User
        - apps.accounts.models.User.is_auditor property
    """

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_auditor:
            return HttpResponseForbidden(
                "You do not have permission to access this page. "
                "Only auditors can view audit logs."
            )
        return view_func(request, *args, **kwargs)

    return wrapper
