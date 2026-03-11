from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Donor
from .forms import DonorForm
from apps.accounts.decorators import write_required


@login_required
def donor_list(request):
    qs = Donor.objects.filter(is_active=True)
    q = request.GET.get("q", "").strip()
    dtype = request.GET.get("type", "")
    if q:
        qs = qs.filter(name__icontains=q)
    if dtype:
        qs = qs.filter(donor_type=dtype)
    return render(request, "donors/donor_list.html", {
        "donors": qs,
        "search_q": q,
        "type_filter": dtype,
        "type_choices": Donor.TYPE_CHOICES,
    })


@login_required
def donor_detail(request, pk):
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    return render(request, "donors/donor_detail.html", {"donor": donor})


@login_required
@write_required
def donor_create(request):
    form = DonorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Donor registered successfully.")
        return redirect("donors:donor_list")
    return render(request, "donors/donor_form.html", {"form": form, "title": "Register Donor"})


@login_required
@write_required
def donor_edit(request, pk):
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    form = DonorForm(request.POST or None, instance=donor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Donor updated successfully.")
        return redirect("donors:donor_detail", pk=pk)
    return render(request, "donors/donor_form.html", {"form": form, "title": "Edit Donor", "object": donor})


@login_required
@write_required
def donor_delete(request, pk):
    donor = get_object_or_404(Donor, pk=pk, is_active=True)
    if request.method == "POST":
        donor.is_active = False
        donor.save()
        messages.success(request, f"Donor '{donor.name}' has been deactivated.")
        return redirect("donors:donor_list")
    return render(request, "donors/donor_confirm_delete.html", {"donor": donor})
