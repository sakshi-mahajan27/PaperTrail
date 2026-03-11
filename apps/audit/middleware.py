"""Middleware that stores the current request user in thread-local storage for audit signals."""
from .utils import set_current_user


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)
        response = self.get_response(request)
        return response
