from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.expenses.models import Expense, ExpenseAllocation
from apps.grants.models import Grant


class Command(BaseCommand):
    help = "Seed sample expenses and allocations data (idempotent)."

    def handle(self, *args, **options):
        created_by = User.objects.filter(role=User.ROLE_FINANCE).order_by("id").first()
        if not created_by:
            raise CommandError(
                "No Finance Manager user found. Create a user with role='finance' first."
            )

        active_grants = list(Grant.objects.filter(is_active=True, status=Grant.STATUS_ACTIVE).order_by("id")[:3])
        if not active_grants:
            raise CommandError("No active grants found. Run: python manage.py seed_grants")

        # Ensure we have 3 grants for allocation examples by repeating the last one if needed.
        while len(active_grants) < 3:
            active_grants.append(active_grants[-1])

        expenses_data = [
            {
                "title": "Medical Camp Supplies - Q1",
                "total_amount": Decimal("250000.00"),
                "expense_date": date(2026, 1, 20),
                "description": "Medicines, diagnostic kits, and basic equipment for community health camps.",
                "receipt": "expenses/receipts/seed/medical_camp_q1.pdf",
                "allocations": [
                    {"grant": active_grants[0], "allocated_amount": Decimal("150000.00")},
                    {"grant": active_grants[1], "allocated_amount": Decimal("100000.00")},
                ],
            },
            {
                "title": "Scholarship Disbursement - January",
                "total_amount": Decimal("180000.00"),
                "expense_date": date(2026, 1, 31),
                "description": "Tuition and study material support for students under education program.",
                "receipt": "expenses/receipts/seed/scholarship_jan.pdf",
                "allocations": [
                    {"grant": active_grants[1], "allocated_amount": Decimal("120000.00")},
                    {"grant": active_grants[2], "allocated_amount": Decimal("60000.00")},
                ],
            },
            {
                "title": "Digital Lab Setup - Batch 1",
                "total_amount": Decimal("420000.00"),
                "expense_date": date(2026, 2, 15),
                "description": "Laptops, networking equipment, and software licenses for youth training center.",
                "receipt": "expenses/receipts/seed/digital_lab_batch1.pdf",
                "allocations": [
                    {"grant": active_grants[0], "allocated_amount": Decimal("220000.00")},
                    {"grant": active_grants[2], "allocated_amount": Decimal("200000.00")},
                ],
            },
            {
                "title": "Field Staff Travel and Logistics",
                "total_amount": Decimal("95000.00"),
                "expense_date": date(2026, 2, 28),
                "description": "Travel reimbursements and logistics support for field monitoring teams.",
                "receipt": "expenses/receipts/seed/field_travel_feb.pdf",
                "allocations": [
                    {"grant": active_grants[0], "allocated_amount": Decimal("50000.00")},
                    {"grant": active_grants[1], "allocated_amount": Decimal("45000.00")},
                ],
            },
            {
                "title": "Community Awareness Workshop",
                "total_amount": Decimal("140000.00"),
                "expense_date": date(2026, 3, 10),
                "description": "Venue, IEC materials, and volunteer support for awareness sessions.",
                "receipt": "expenses/receipts/seed/awareness_workshop_mar.pdf",
                "allocations": [
                    {"grant": active_grants[1], "allocated_amount": Decimal("90000.00")},
                    {"grant": active_grants[2], "allocated_amount": Decimal("50000.00")},
                ],
            },
        ]

        created_expenses = 0
        created_allocations = 0

        with transaction.atomic():
            for row in expenses_data:
                expense, expense_created = Expense.objects.get_or_create(
                    title=row["title"],
                    total_amount=row["total_amount"],
                    expense_date=row["expense_date"],
                    defaults={
                        "description": row["description"],
                        "receipt": row["receipt"],
                        "created_by": created_by,
                        "is_active": True,
                    },
                )

                if expense_created:
                    created_expenses += 1

                for allocation in row["allocations"]:
                    _, allocation_created = ExpenseAllocation.objects.get_or_create(
                        expense=expense,
                        grant=allocation["grant"],
                        defaults={"allocated_amount": allocation["allocated_amount"]},
                    )
                    if allocation_created:
                        created_allocations += 1

        self.stdout.write(self.style.SUCCESS(f"Created expenses: {created_expenses}"))
        self.stdout.write(self.style.SUCCESS(f"Created allocations: {created_allocations}"))
        self.stdout.write(self.style.SUCCESS(f"Total expenses: {Expense.objects.count()}"))
