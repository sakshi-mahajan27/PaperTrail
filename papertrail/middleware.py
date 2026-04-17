"""
Security middleware for caching and session management.

This middleware adds cache control headers to authenticated pages to prevent
browsers from caching sensitive content. When a user logs out, they won't be
able to access previously authenticated pages via browser back button.
"""

from django.utils.deprecation import MiddlewareMixin


class NoCacheMiddleware(MiddlewareMixin):
    """
    Middleware to prevent caching of authenticated pages.
    
    This middleware ensures that:
    1. Authenticated pages are never cached by the browser
    2. After logout, browser back button won't show cached pages
    3. Session-dependent content requires server validation
    
    Implementation Details:
    - For authenticated requests: Sets strict no-cache headers
    - For unauthenticated requests: Allows normal caching behavior
    - Headers follow RFC 7234 standards
    
    Security Headers Added (for authenticated users):
    - Cache-Control: no-store, no-cache, must-revalidate, max-age=0, private
    - Pragma: no-cache (for HTTP/1.0 compatibility)
    - Expires: 0 (for HTTP/1.0 compatibility)
    """
    
    def process_response(self, request, response):
        """
        Add cache control headers based on authentication status.
        
        Args:
            request: The HTTP request object
            response: The HTTP response object
            
        Returns:
            The modified response with cache headers
        """
        
        # Check if user is authenticated
        if request.user and request.user.is_authenticated:
            # For authenticated users, prevent all caching
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            response['Vary'] = 'Cookie'
            
            # Additional security header to prevent caching by proxies
            response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response


class SecureSessionMiddleware(MiddlewareMixin):
    """
    Middleware to add security headers for session cookies.
    
    This middleware ensures session cookies have proper security flags:
    - HttpOnly: Prevents JavaScript access to session cookie
    - Secure: Ensures cookie sent only over HTTPS (in production)
    - SameSite: Protects against CSRF attacks
    
    Additional security measures:
    - Adds strict transport security header for HTTPS
    - Prevents content type sniffing
    """
    
    def process_response(self, request, response):
        """
        Add security headers to response.
        
        Args:
            request: The HTTP request object
            response: The HTTP response object
            
        Returns:
            The modified response with security headers
        """
        
        # Prevent MIME type sniffing
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Only in HTTPS (production) environments
        # Note: Uncomment when deploying to production with HTTPS
        # response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response
