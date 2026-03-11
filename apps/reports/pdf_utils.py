from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa


def render_pdf_response(template_name, context, filename="report.pdf", request=None):
    """Render a Django template to a PDF HTTP response using xhtml2pdf."""
    html = render_to_string(template_name, context, request=request)
    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buffer, encoding="UTF-8")
    if pisa_status.err:
        return HttpResponse(
            "PDF generation failed. Please contact the administrator.",
            status=500,
            content_type="text/plain",
        )
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
