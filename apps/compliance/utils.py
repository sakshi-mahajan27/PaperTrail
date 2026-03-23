from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from .models import ComplianceDocument


def send_yellow_alert_email(doc):
    """
    Send email alert to admins when a compliance document is expiring soon (yellow status).

    This function is called when a certificate enters 'yellow' status (will expire
    within 180 days). It sends an HTML email to all admin users notifying them
    that the certificate needs renewal.

    Args:
        doc (ComplianceDocument): The certificate that is expiring soon

    Returns:
        bool: True if email sent successfully, False otherwise

    Email Recipients:
        All users with role='admin' who have filled in their email address.
        If no admins have emails, returns False without sending.

    Email Format:
        - From: settings.DEFAULT_FROM_EMAIL (e.g., noreply@papertrail.org)
        - Subject: "Certificate Alert: {CERT_TYPE} Expiring Soon"
        - Body: HTML from compliance/notification_email.html template
        - Fallback: Plain text if template missing

    Email Context:
        Template receives:
        - document: The ComplianceDocument object
        - days_to_expiry: Computed from (expiry_date - today).days
        - expiry_date: From document

    Error Handling:
        - If no admin emails available: Returns False silently
        - If template missing: Uses fallback plain text message
        - If email send fails: Exception caught, returns False

    Example Usage:
        # Called manually if needed
        doc = ComplianceDocument.objects.get(cert_type='FCRA')
        if doc.status == 'yellow' and not doc.yellow_alert_sent:
            send_yellow_alert_email(doc)

        # Usually called by Celery task (tasks.py)

    Notes:
        - Does NOT update yellow_alert_sent timestamp (that's in the Celery task)
        - Called by send_yellow_alert_email_task Celery task in tasks.py
        - Fire-and-forget design (errors caught and logged)
        - Idempotent call: can be called multiple times safely
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
    Check if the NGO is currently in compliance.

    This is the PRIMARY COMPLIANCE GATE for the application. It returns True
    only if ALL three mandatory certificates (FCRA, 80G, 12A) exist and NONE
    of them are expired (red status).

    Return Value:
        bool: True if compliant, False otherwise

    Compliance Rules:
        ✓ MUST have FCRA certificate  → expiry_date > today
        ✓ MUST have 80G certificate  → expiry_date > today
        ✓ MUST have 12A certificate  → expiry_date > today
        ✗ ANY expired certificate    → FAIL (red status)
        ✗ ANY certificate missing    → FAIL
        ✓ Yellow status OK (≤180 days to expiry) → Still compliant

    Business Logic:
        The system uses tri-color status:
        - 'green' (>180 days): Fully compliant
        - 'yellow' (≤180 days): Still compliant but warning sent
        - 'red' (expired): NON-COMPLIANT

        This function checks: All exist AND none are 'red'

    Where Used (Compliance Gates):
        1. ExpenseForm.clean() in expenses/forms.py
           → Cannot create/edit expense if not is_compliant()
           → Error message: "Compliance gate failed: {issues}"

        2. GrantForm.clean() in grants/views.py (grant_create view)
           → Cannot create grant if not is_compliant()
           → Redirects with error message

        3. grant_create view in grants/views.py
           → Checks before rendering form
           → Displays issue list to user

    Example Return Values:
        Scenario 1: All valid (green)
            docs = [FCRA(green), 80G(green), 12A(green)]
            is_compliant() → True

        Scenario 2: All exist but one expired (red)
            docs = [FCRA(green), 80G(red), 12A(green)]
            is_compliant() → False (because 80G is red)

        Scenario 3: Missing one certificate
            docs = [FCRA(green), 12A(green)]  # 80G missing
            is_compliant() → False

        Scenario 4: One expiring soon (yellow) - still compliant!
            docs = [FCRA(green), 80G(yellow), 12A(green)]
            is_compliant() → True (yellow is OK)

    Performance Notes:
        - Runs O(n) where n ≤ 3 (only 3 certs can exist)
        - No database indexes needed (small dataset)
        - Called on every: expense_create, expense_edit, grant_create
        - In production, could add Redis caching for 1-hour TTL

    Implementation:
        1. Get set of required cert types: {FCRA, 80G, 12A}
        2. Fetch all ComplianceDocument objects
        3. Check if all required types exist
        4. Check that none have 'red' status (expired)

    See Also:
        - get_compliance_issues() - Returns human-readable error list
        - ComplianceDocument.status property - Computed via expiry_date
        - send_yellow_alert_email_task (tasks.py) - Celery task for alerts
    """
    required = {ComplianceDocument.FCRA, ComplianceDocument.G80, ComplianceDocument.A12}
    docs = ComplianceDocument.objects.all()
    found = {d.cert_type: d for d in docs}

    if not required.issubset(found.keys()):
        # One or more certificate types are missing entirely
        return False

    return all(doc.status != "red" for doc in found.values())


def get_compliance_issues():
    """
    Return a list of human-readable compliance issue strings.

    This function identifies all reasons why is_compliant() might return False,
    and returns them as a list of English error messages suitable for display
    to users or in alerts.

    Return Value:
        list: List of issue strings, empty list if fully compliant

    Issue Types Detected:
        1. Missing certificate: "{CERT_TYPE} is missing."
           → For each of FCRA, 80G, 12A that don't exist
        2. Expired certificate: "{CERT_TYPE} ({expiry_date}) has expired."
           → For each certificate with status='red'

    Example Returns:
        Scenario 1: Fully compliant
            get_compliance_issues() → []

        Scenario 2: Missing 80G and FCRA expired
            get_compliance_issues() → [
                "FCRA Certificate (2023-03-01) has expired.",
                "80G Certificate is missing."
            ]

        Scenario 3: Missing all (new NGO)
            get_compliance_issues() → [
                "FCRA Certificate is missing.",
                "80G Certificate is missing.",
                "12A Certificate is missing."
            ]

        Scenario 4: One expiring soon (yellow) - no issues
            get_compliance_issues() → []  # Yellow is OK

    Used By:
        1. Exception messages in form validation:
           → raise ValidationError("Compliance failed: " + " | ".join(issues))

        2. Redirect messages in views:
           → messages.error(request, "Issues: " + " | ".join(issues))

        3. Email alerts:
           → Send details of what needs to be done

    Format Notes:
        - Each issue is a complete sentence (starts with noun, ends with period)
        - Suitable for direct insertion into error/alert messages
        - Human-readable: uses get_cert_type_display() (e.g., "80G Certificate")
        - Includes dates for expired certs to help admin prioritize

    Implementation:
        1. Get required cert types: {FCRA, 80G, 12A}
        2. Fetch all documents and build {type: doc} dict
        3. For each required type:
           - If missing: add "X is missing."
           - If found but expired (red): add "X has expired."
        4. Return list of issues

    See Also:
        - is_compliant() - Returns True/False overall
        - ComplianceDocument.status - Computed property (green/yellow/red)
        - ExpenseForm.clean() - Uses this to build error messages
    """
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
