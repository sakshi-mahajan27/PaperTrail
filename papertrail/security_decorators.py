"""
Decorators for security and cache control in PaperTrail.

These decorators provide additional security measures for sensitive views,
including cache prevention and response headers.
"""

from functools import wraps
from django.views.decorators.http import condition
from django.utils.http import http_date


def no_cache(view_func):
    """
    Decorator to prevent caching of a view response.
    
    Adds cache control headers to ensure:
    - Response is not cached by browsers
    - Response is not cached by proxies
    - Session/authentication state is respected
    
    Usage:
        @login_required
        @no_cache
        def sensitive_view(request):
            return render(request, 'sensitive.html')
    
    Note:
        - Should be placed after @login_required
        - Works in conjunction with NoCacheMiddleware
        - Headers added: Cache-Control, Pragma, Expires
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        
        # Prevent caching at all levels
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['Vary'] = 'Cookie'
        
        return response
    
    return wrapped_view


def secure_session_required(view_func):
    """
    Decorator to ensure secure session and prevent caching.
    
    This decorator combines login_required functionality with cache prevention
    and session validation. It's useful for highly sensitive views.
    
    Usage:
        @secure_session_required
        def admin_view(request):
            return render(request, 'admin.html')
    
    Benefits:
    - Validates session is still active
    - Prevents caching of response
    - Adds security headers
    - Ensures user is authenticated
    """
    from django.contrib.auth.decorators import login_required
    
    @wraps(view_func)
    @login_required
    @no_cache
    def wrapped_view(request, *args, **kwargs):
        # Additional session validation
        if not request.session.get('_auth_user_id'):
            from django.contrib.auth import logout
            logout(request)
            from django.shortcuts import redirect
            from django.contrib import messages
            messages.warning(request, 'Your session has expired. Please log in again.')
            return redirect('accounts:login')
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view
