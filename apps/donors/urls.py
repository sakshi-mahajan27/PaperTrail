from django.urls import path
from . import views

app_name = "donors"

urlpatterns = [
    path("", views.donor_list, name="donor_list"),
    path("create/", views.donor_create, name="donor_create"),
    path("<int:pk>/", views.donor_detail, name="donor_detail"),
    path("<int:pk>/edit/", views.donor_edit, name="donor_edit"),
    path("<int:pk>/delete/", views.donor_delete, name="donor_delete"),
]
