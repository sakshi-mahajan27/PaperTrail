from django.db import models


class Donor(models.Model):
    """
    Registry of organizations and individuals who donate funds to the NGO.

    This model tracks donors (individuals, organizations, governments, corporates)
    who contribute funds. Each donor can fund multiple grants, allowing flexible
    grant allocation across different donor relationships.

    Business Purpose:
        - Build a donor database for grant tracking
        - Link grants to their funding source (who gave the money)
        - Track donor contact information for follow-ups
        - Identify donor types (individual, corporate, government, etc.)

    Soft Deletion:
        Donors use 'is_active' flag (soft delete) rather than true deletion.
        This preserves historical data when a donor relationship ends.
        Soft-deleted donors still appear in reports but can be filtered out.

    Fields:
        name (str): Donor organization or person name.
            Required, max 200 chars.
            Examples: "ABC Foundation", "John Smith", "Department of Health"

        donor_type (str): Category of donor.
            One of 'individual', 'organization', 'government', 'corporate'
            Defaults to 'individual'
            Useful for categorization and filtering

        email (str): Donor contact email address.
            Optional, for communication
            Can be blank if not available

        phone (str): Donor contact phone number.
            Optional, max 20 chars
            Format not enforced (international variations)

        country (str): Donor's country.
            Defaults to 'India' (common NGO context)
            Max 100 chars

        address (str): Full mailing address.
            Optional, for communication/records
            TextField allows multi-line

        pan_number (str): Donor's PAN (Permanent Account Number).
            India-specific tax identifier
            Optional, max 20 chars
            Useful for compliance with Indian tax authorities

        notes (str): Internal notes about the donor.
            Optional, free text
            For tracking donation preferences, restrictions, etc.

        is_active (bool): Soft-delete flag.
            Default=True (active)
            False = deactivated (but data preserved)
            Filtered in views using is_active=True

        created_at (datetime): Auto-set on creation.
            Never changes after creation

        updated_at (datetime): Auto-updated on every save.
            Tracks last modification time

    Metadata:
        ordering: By name (alphabetical for easy navigation)

    Query Examples:
        # Get all active donors
        active = Donor.objects.filter(is_active=True)

        # Get donors of a specific type
        corporates = Donor.objects.filter(is_active=True, donor_type='corporate')

        # Find a donor by name
        donor = Donor.objects.get(name='ABC Foundation', is_active=True)

        # Get donors who have active grants
        from apps.grants.models import Grant
        grant = Grant.objects.get(status='active')
        donor = grant.donor

    Performance Notes:
        - ordering=['name']: No database index needed (small dataset)
        - Soft deletes via is_active: Must filter in views (no automatic filtering)
        - No select_related needed unless accessing related grants
        - Count query: Donor.objects.filter(is_active=True).count()

    Relationships:
        - Reverse FK: grants (from Grant model)
            Allows accessing donor.grants.all()

    Security Considerations:
        - PAN number stored as text (should use encryption in production)
        - Email/phone available to admins only (via role_required decorators)
        - No sensitive financial data stored directly (stored in Grants)

    Example Lifecycle:
        1. Admin registers "Save the Children" as corporate donor
        2. Creates grant: "Child Education Program" ($100,000)
        3. Creates expenses and allocations against that grant
        4. Reports show "Save the Children" as funding source
        5. When partnership ends, mark is_active=False (soft delete)
        6. Historical data preserved for audits
    """

    TYPE_INDIVIDUAL = "individual"
    TYPE_ORGANIZATION = "organization"
    TYPE_GOVERNMENT = "government"
    TYPE_CORPORATE = "corporate"

    TYPE_CHOICES = [
        (TYPE_INDIVIDUAL, "Individual"),
        (TYPE_ORGANIZATION, "Organization"),
        (TYPE_GOVERNMENT, "Government"),
        (TYPE_CORPORATE, "Corporate"),
    ]

    name = models.CharField(
        max_length=200,
        help_text="Full name of the donor (individual, organization, or agency)"
    )
    donor_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_INDIVIDUAL,
        help_text="Category of donor for classification"
    )
    email = models.EmailField(
        blank=True,
        help_text="Contact email address"
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact phone number (format flexible)"
    )
    country = models.CharField(
        max_length=100,
        default="India",
        help_text="Donor's country"
    )
    address = models.TextField(
        blank=True,
        help_text="Mailing address for communication"
    )
    pan_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="PAN Number",
        help_text="Indian PAN (Permanent Account Number) for tax purposes"
    )
    notes = models.TextField(
        blank=True,
        help_text="Internal notes (preferences, restrictions, etc.)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag. False = inactive but preserved for history"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the donor was first registered"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the donor record was last modified"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_donor_type_display()})"
