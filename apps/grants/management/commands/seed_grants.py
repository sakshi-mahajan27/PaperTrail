from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.donors.models import Donor
from apps.grants.models import Grant


class Command(BaseCommand):
    help = "Seed sample grant data (idempotent)."

    def handle(self, *args, **options):
        grants_data = [
            {
                "donor_name": "Yashoda Foundation",
                "donor_type": Donor.TYPE_ORGANIZATION,
                "name": "Community Health Outreach 2026",
                "total_amount": Decimal("1500000.00"),
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "purpose": "Primary healthcare camps, maternal health awareness, and medicine support in rural districts.",
                "status": Grant.STATUS_ACTIVE,
            },
            {
                "donor_name": "Bright Future Trust",
                "donor_type": Donor.TYPE_ORGANIZATION,
                "name": "Girls Education Scholarship Program",
                "total_amount": Decimal("900000.00"),
                "start_date": date(2025, 7, 1),
                "end_date": date(2026, 6, 30),
                "purpose": "Scholarships, learning materials, and mentoring for adolescent girls in low-income families.",
                "status": Grant.STATUS_ACTIVE,
            },
            {
                "donor_name": "Green Earth Initiative",
                "donor_type": Donor.TYPE_ORGANIZATION,
                "name": "Water and Sanitation Improvement Project",
                "total_amount": Decimal("2200000.00"),
                "start_date": date(2026, 4, 1),
                "end_date": date(2027, 3, 31),
                "purpose": "Construction of sanitation units and village-level hygiene awareness campaigns.",
                "status": Grant.STATUS_PENDING,
            },
            {
                "donor_name": "Navjyoti Corporate CSR",
                "donor_type": Donor.TYPE_CORPORATE,
                "name": "Digital Literacy for Youth",
                "total_amount": Decimal("1250000.00"),
                "start_date": date(2025, 10, 1),
                "end_date": date(2026, 9, 30),
                "purpose": "Computer lab setup, digital skills training, and placement support for youth.",
                "status": Grant.STATUS_ACTIVE,
            },
            {
                "donor_name": "State Social Welfare Department",
                "donor_type": Donor.TYPE_GOVERNMENT,
                "name": "Nutrition Support for Children",
                "total_amount": Decimal("3000000.00"),
                "start_date": date(2025, 4, 1),
                "end_date": date(2026, 3, 31),
                "purpose": "Supplementary nutrition kits and growth monitoring for under-5 children.",
                "status": Grant.STATUS_CLOSED,
            },
            {
                "donor_name": "Hope International",
                "donor_type": Donor.TYPE_ORGANIZATION,
                "name": "Emergency Relief and Rehabilitation",
                "total_amount": Decimal("1800000.00"),
                "start_date": date(2026, 6, 1),
                "end_date": date(2027, 5, 31),
                "purpose": "Rapid relief support and rehabilitation services for flood-affected families.",
                "status": Grant.STATUS_PENDING,
            },
        ]

        created_donors = 0
        created_grants = 0

        with transaction.atomic():
            for row in grants_data:
                donor, donor_created = Donor.objects.get_or_create(
                    name=row["donor_name"],
                    defaults={
                        "donor_type": row["donor_type"],
                        "is_active": True,
                    },
                )
                if donor_created:
                    created_donors += 1

                _, grant_created = Grant.objects.get_or_create(
                    donor=donor,
                    name=row["name"],
                    defaults={
                        "total_amount": row["total_amount"],
                        "start_date": row["start_date"],
                        "end_date": row["end_date"],
                        "purpose": row["purpose"],
                        "status": row["status"],
                        "is_active": True,
                    },
                )
                if grant_created:
                    created_grants += 1

        self.stdout.write(self.style.SUCCESS(f"Created donors: {created_donors}"))
        self.stdout.write(self.style.SUCCESS(f"Created grants: {created_grants}"))
        self.stdout.write(self.style.SUCCESS(f"Total grants: {Grant.objects.count()}"))
