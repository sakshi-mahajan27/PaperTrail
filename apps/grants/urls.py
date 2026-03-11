from django.urls import path
from . import views

app_name = "grants"

urlpatterns = [
    path("", views.grant_list, name="grant_list"),
    path("create/", views.grant_create, name="grant_create"),
    path("<int:pk>/", views.grant_detail, name="grant_detail"),
    path("<int:pk>/edit/", views.grant_edit, name="grant_edit"),
    path("<int:pk>/close/", views.grant_close, name="grant_close"),
]
