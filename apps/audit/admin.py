from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for audit logs.
    Audit logs cannot be edited or deleted.
    """

    list_display = ('timestamp', 'action', 'object_repr', 'model_name', 'changed_by')
    list_filter = ('action', 'content_type', 'timestamp', 'changed_by')
    search_fields = ('object_repr', 'changed_by__username')
    readonly_fields = (
        'action', 'content_type', 'object_id', 'object_repr',
        'changed_by', 'timestamp', 'changes'
    )
    ordering = ['-timestamp']

    # Make the model completely read-only
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
