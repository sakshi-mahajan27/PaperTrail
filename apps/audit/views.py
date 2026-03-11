from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import AuditLog
from apps.accounts.models import User


@login_required
def audit_log_list(request):
    logs = AuditLog.objects.select_related("user")

    # filters
    action_filter = request.GET.get("action", "")
    model_filter = request.GET.get("model", "")
    user_filter = request.GET.get("user", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    if action_filter:
        logs = logs.filter(action=action_filter)
    if model_filter:
        logs = logs.filter(model_name=model_filter)
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    model_names = AuditLog.objects.values_list("model_name", flat=True).distinct()

    context = {
        "logs": logs[:200],
        "action_choices": AuditLog.ACTION_CHOICES,
        "model_names": sorted(set(model_names)),
        "action_filter": action_filter,
        "model_filter": model_filter,
        "user_filter": user_filter,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "audit/audit_log_list.html", context)


@login_required
def audit_log_detail(request, pk):
    log = get_object_or_404(AuditLog, pk=pk)
    return render(request, "audit/audit_log_detail.html", {"log": log})
