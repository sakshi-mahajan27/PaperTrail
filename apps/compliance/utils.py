from .models import ComplianceDocument


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
