from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from .models import AuditLog
from .decorators import auditor_required
import json


@auditor_required
def audit_log_list(request):
    """
    View audit logs with search and filtering capabilities.
    Only accessible to users with auditor role.
    """
    logs = AuditLog.objects.all()

    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        logs = logs.filter(
            Q(object_repr__icontains=search_query) |
            Q(changed_by__first_name__icontains=search_query) |
            Q(changed_by__last_name__icontains=search_query) |
            Q(changed_by__username__icontains=search_query)
        )

    # Filter by action
    action_filter = request.GET.get('action', '').strip()
    if action_filter and action_filter in dict(AuditLog.ACTION_CHOICES):
        logs = logs.filter(action=action_filter)

    # Filter by model
    model_filter = request.GET.get('model', '').strip()
    if model_filter:
        logs = logs.filter(content_type__model=model_filter)

    # Get unique models for filter dropdown
    from django.contrib.contenttypes.models import ContentType
    models = ContentType.objects.filter(
        auditlog__isnull=False
    ).values('model', 'app_label').distinct().order_by('app_label', 'model')

    # Pagination
    paginator = Paginator(logs, 50)  # Show 50 logs per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'action_filter': action_filter,
        'model_filter': model_filter,
        'action_choices': AuditLog.ACTION_CHOICES,
        'models': models,
    }

    return render(request, 'audit/audit_log_list.html', context)


@auditor_required
def audit_log_detail(request, log_id):
    """
    Return JSON details for a specific audit log.
    Used for modal display via AJAX.
    """
    try:
        log = AuditLog.objects.get(id=log_id)
    except AuditLog.DoesNotExist:
        return JsonResponse({'error': 'Audit log not found'}, status=404)

    # Format the response
    response_data = {
        'id': log.id,
        'action': log.get_action_display(),
        'action_raw': log.action,
        'object': log.object_repr,
        'model': log.model_label,
        'user': str(log.changed_by) if log.changed_by else 'System',
        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'changes': log.changes,
    }

    return JsonResponse(response_data)
