from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST

from .forms import LoginForm, UserCreateForm, UserUpdateForm
from .models import User
from .decorators import role_required


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get("next", "accounts:dashboard"))
        messages.error(request, "Invalid username or password.")
    return render(request, "accounts/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
def dashboard_view(request):
    from apps.compliance.models import ComplianceDocument
    from apps.grants.models import Grant
    from apps.expenses.models import Expense

    docs = ComplianceDocument.objects.all()
    compliance_summary = {
        "green": sum(1 for d in docs if d.status == "green"),
        "yellow": sum(1 for d in docs if d.status == "yellow"),
        "red": sum(1 for d in docs if d.status == "red"),
    }
    active_grants = Grant.objects.filter(is_active=True, status="active")
    recent_expenses = Expense.objects.filter(is_active=True).select_related("created_by").order_by("-created_at")[:10]

    context = {
        "compliance_summary": compliance_summary,
        "active_grants": active_grants,
        "recent_expenses": recent_expenses,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
@role_required("admin")
def user_list(request):
    users = User.objects.all().order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@role_required("admin")
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User created successfully.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Create User"})


@login_required
@role_required("admin")
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserUpdateForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User updated successfully.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Edit User", "object": user})


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html", {"user_obj": request.user})
