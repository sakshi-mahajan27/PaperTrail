from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Grant
from .forms import GrantForm
from apps.accounts.decorators import role_required, finance_required
from apps.compliance.utils import is_compliant, get_compliance_issues


@login_required
@role_required("admin", "finance")
def grant_list(request):
    grants = Grant.objects.filter(is_active=True).select_related("donor")
    status_filter = request.GET.get("status", "")
    if status_filter:
        grants = grants.filter(status=status_filter)
    return render(request, "grants/grant_list.html", {
        "grants": grants,
        "status_filter": status_filter,
        "status_choices": Grant.STATUS_CHOICES,
    })


@login_required
@role_required("admin", "finance")
def grant_detail(request, pk):
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    allocations = grant.allocations.filter(expense__is_active=True).select_related("expense")
    return render(request, "grants/grant_detail.html", {"grant": grant, "allocations": allocations})


@login_required
@finance_required
def grant_create(request):
    if not is_compliant():
        issues = get_compliance_issues()
        messages.error(request, "Cannot create a grant. Compliance issues: " + " | ".join(issues))
        return redirect("grants:grant_list")

    form = GrantForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grant created successfully.")
        return redirect("grants:grant_list")
    return render(request, "grants/grant_form.html", {"form": form, "title": "Create Grant"})


@login_required
@finance_required
def grant_edit(request, pk):
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    form = GrantForm(request.POST or None, request.FILES or None, instance=grant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grant updated successfully.")
        return redirect("grants:grant_detail", pk=pk)
    return render(request, "grants/grant_form.html", {"form": form, "title": "Edit Grant", "object": grant})


@login_required
@finance_required
def grant_close(request, pk):
    grant = get_object_or_404(Grant, pk=pk, is_active=True)
    if request.method == "POST":
        grant.status = Grant.STATUS_CLOSED
        grant.save()
        messages.success(request, f"Grant '{grant.name}' has been closed.")
        return redirect("grants:grant_list")
    return render(request, "grants/grant_confirm_close.html", {"grant": grant})
