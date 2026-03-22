from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('logs/', views.audit_log_list, name='log_list'),
    path('logs/<int:log_id>/detail/', views.audit_log_detail, name='log_detail'),
]
