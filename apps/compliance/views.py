from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import ComplianceDocument
from .forms import ComplianceDocumentForm
from apps.accounts.decorators import role_required


@login_required
def document_list(request):
    docs = ComplianceDocument.objects.all()
    return render(request, "compliance/document_list.html", {"docs": docs})


@login_required
@role_required("admin")
def document_upload(request):
    form = ComplianceDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        doc.uploaded_by = request.user
        doc.save()
        messages.success(request, f"{doc.get_cert_type_display()} uploaded successfully.")
        return redirect("compliance:document_list")
    return render(request, "compliance/document_form.html", {"form": form, "title": "Upload Certificate"})


@login_required
@role_required("admin")
def document_edit(request, pk):
    doc = get_object_or_404(ComplianceDocument, pk=pk)
    form = ComplianceDocumentForm(request.POST or None, request.FILES or None, instance=doc)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Certificate updated successfully.")
        return redirect("compliance:document_list")
    return render(request, "compliance/document_form.html", {"form": form, "title": "Edit Certificate", "object": doc})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(ComplianceDocument, pk=pk)
    return render(request, "compliance/document_detail.html", {"doc": doc})
