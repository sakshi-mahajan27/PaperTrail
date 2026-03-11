from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    """Restrict view to users whose role is in the given list."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, "You do not have permission to access this page.")
                return redirect("accounts:dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def write_required(view_func):
    """Restrict view to Admin and Finance Manager (anyone who can write)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.can_write:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("accounts:dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped
