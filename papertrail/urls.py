from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from . import error_views

handler400 = error_views.bad_request
handler403 = error_views.permission_denied
handler404 = error_views.page_not_found
handler500 = error_views.server_error

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("compliance/", include("apps.compliance.urls", namespace="compliance")),
    path("donors/", include("apps.donors.urls", namespace="donors")),
    path("grants/", include("apps.grants.urls", namespace="grants")),
    path("expenses/", include("apps.expenses.urls", namespace="expenses")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    # Root redirect → dashboard
    path("", RedirectView.as_view(url="/accounts/dashboard/", permanent=False)),
    path("dashboard/", RedirectView.as_view(url="/accounts/dashboard/", permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
