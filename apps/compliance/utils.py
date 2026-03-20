from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from .models import ComplianceDocument


def send_yellow_alert_email(doc):
    """
    Send email alert to admins when a compliance document is expiring soon (yellow status).
    """
    try:
        # Get all admin users
        from apps.accounts.models import User
        admins = User.objects.filter(role='admin')
        admin_emails = [admin.email for admin in admins if admin.email]
        
        if not admin_emails:
            return False
        
        subject = f"Certificate Alert: {doc.get_cert_type_display()} Expiring Soon"
        
        # Create email context
        context = {
            "document": doc,
            "days_to_expiry": doc.days_to_expiry,
            "expiry_date": doc.expiry_date,
        }
        
        # Try to render from template, fallback to plain text
        try:
            message = render_to_string('compliance/notification_email.html', context)
            html_message = message
        except:
            message = f"""
            Alert: {doc.get_cert_type_display()} is expiring soon!
            
            Certificate Details:
            - Type: {doc.get_cert_type_display()}
            - Expiry Date: {doc.expiry_date}
            - Days Until Expiry: {doc.days_to_expiry}
            - Status: {doc.status_label}
            
            Please take action to renew or replace this certificate.
            """
            html_message = None
        
        # Send email
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            admin_emails,
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
    except Exception as e:
        print(f"Error sending yellow alert email: {e}")
        return False


def is_compliant():
    """
    Returns True only if all three required certificate types exist
    and none of them are in 'red' (expired) status.
    """
    required = {ComplianceDocument.FCRA, ComplianceDocument.G80, ComplianceDocument.A12}
    docs = ComplianceDocument.objects.all()
    found = {d.cert_type: d for d in docs}

    if not required.issubset(found.keys()):
        # One or more certificate types are missing entirely
        return False

    return all(doc.status != "red" for doc in found.values())


def get_compliance_issues():
    """Return a list of human-readable compliance issue strings."""
    required = {ComplianceDocument.FCRA, ComplianceDocument.G80, ComplianceDocument.A12}
    docs = ComplianceDocument.objects.all()
    found = {d.cert_type: d for d in docs}
    issues = []

    for cert_type in required:
        if cert_type not in found:
            label = dict(ComplianceDocument.CERT_TYPE_CHOICES).get(cert_type, cert_type)
            issues.append(f"{label} is missing.")
        elif found[cert_type].status == "red":
            issues.append(f"{found[cert_type]} has expired.")

    return issues
