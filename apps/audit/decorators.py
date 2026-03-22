from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponseForbidden


def auditor_required(view_func):
    """
    Decorator to ensure only users with auditor role can access the view.
    Redirects to login if not authenticated.
    Returns 403 Forbidden if not an auditor.
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
