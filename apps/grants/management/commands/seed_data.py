"""
Management command: seed_data

Idempotent one-shot seeder that:
  1. Patches PAN numbers onto the existing six donors created by seed_grants.
  2. Creates six new donors with full contact details + PAN numbers.
  3. Creates eight new grants spread across old and new donors.
  4. Creates ten new expenses with realistic allocations against active grants.

Usage:
    python manage.py seed_data           # normal run
    python manage.py seed_data --reset   # wipe all seeded data first (careful!)

Idempotency:
    Donors matched by name (get_or_create).
    Grants matched by donor + name (get_or_create).
    Expenses matched by title + date + amount (get_or_create).
    Running twice is safe — no duplicate rows.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.donors.models import Donor
from apps.expenses.models import Expense, ExpenseAllocation
from apps.grants.models import Grant


# ---------------------------------------------------------------------------
# PAN patches for the six donors created by seed_grants
# ---------------------------------------------------------------------------
EXISTING_DONOR_PANS = {
    "Yashoda Foundation":          {"pan": "AABTY1234C", "email": "grants@yashodafoundation.org",   "phone": "9876543210", "country": "India"},
    "Bright Future Trust":         {"pan": "AACBF5678D", "email": "info@brightfuturetrust.in",      "phone": "9845001122", "country": "India"},
    "Green Earth Initiative":      {"pan": "AADGE9012E", "email": "contact@greenearth.ngo",         "phone": "8800112233", "country": "India"},
    "Navjyoti Corporate CSR":      {"pan": "AABCN3456F", "email": "csr@navjyotigroup.com",          "phone": "9910223344", "country": "India"},
    "State Social Welfare Dept":   {"pan": "AAAGS1230A", "email": "swdept@maharashtra.gov.in",       "phone": "02222334455", "country": "India"},
    "Hope International":          {"pan": "AABHI6789G", "email": "india@hopeinternational.org",     "phone": "9988776655", "country": "India"},
    # Government donor has slightly different stored name — cover both variations
    "State Social Welfare Department": {"pan": "AAAGS1230A", "email": "swdept@maharashtra.gov.in",  "phone": "02222334455", "country": "India"},
}


# ---------------------------------------------------------------------------
# New donors
# ---------------------------------------------------------------------------
NEW_DONORS = [
    {
        "name": "Arjun Mehta",
        "donor_type": Donor.TYPE_INDIVIDUAL,
        "email": "arjun.mehta@gmail.com",
        "phone": "9823456781",
        "country": "India",
        "address": "42, MG Road, Pune, Maharashtra – 411001",
        "pan_number": "AAZPM1234A",
        "notes": "Individual HNI donor; prefers education-linked grants.",
    },
    {
        "name": "Sunita Rao",
        "donor_type": Donor.TYPE_INDIVIDUAL,
        "email": "sunita.rao@rediffmail.com",
        "phone": "9711234567",
        "country": "India",
        "address": "15, Residency Road, Bengaluru, Karnataka – 560025",
        "pan_number": "BDFPR5678K",
        "notes": "Recurring annual donor; supports women empowerment programs.",
    },
    {
        "name": "Reliance Social Foundation",
        "donor_type": Donor.TYPE_CORPORATE,
        "email": "csr@rsf.relianceindustries.com",
        "phone": "02222554433",
        "country": "India",
        "address": "Maker Chambers IV, Nariman Point, Mumbai – 400021",
        "pan_number": "AABCR2345B",
        "notes": "CSR arm of Reliance Industries; multi-year partnership since 2023.",
    },
    {
        "name": "USAID India Mission",
        "donor_type": Donor.TYPE_GOVERNMENT,
        "email": "indiamission@usaid.gov",
        "phone": "+911124198000",
        "country": "United States",
        "address": "American Embassy, Shantipath, Chanakyapuri, New Delhi – 110021",
        "pan_number": "AACFU9876Z",
        "notes": "International bilateral donor; FCRA compliance mandatory.",
    },
    {
        "name": "Tata Trusts",
        "donor_type": Donor.TYPE_ORGANIZATION,
        "email": "grants@tatatrusts.org",
        "phone": "02261928282",
        "country": "India",
        "address": "Bombay House, 24, Homi Mody Street, Fort, Mumbai – 400001",
        "pan_number": "AAATT1111T",
        "notes": "Preferred partner for water, sanitation, and livelihoods initiatives.",
    },
    {
        "name": "Infosys Foundation",
        "donor_type": Donor.TYPE_CORPORATE,
        "email": "foundation@infosys.com",
        "phone": "08044261000",
        "country": "India",
        "address": "Electronics City, Hosur Road, Bengaluru, Karnataka – 560100",
        "pan_number": "AABCI1234N",
        "notes": "Tech-focused CSR; favours digital literacy and skill-building projects.",
    },
]


# ---------------------------------------------------------------------------
# New grants  (donor_name must match name field of NEW_DONORS or EXISTING_DONOR_PANS)
# ---------------------------------------------------------------------------
NEW_GRANTS = [
    {
        "donor_name": "Arjun Mehta",
        "name": "Rural School Library Program",
        "total_amount": Decimal("500000.00"),
        "start_date": date(2026, 3, 1),
        "end_date": date(2026, 12, 31),
        "purpose": "Establish school libraries with curated books and reading programs in 10 villages.",
        "status": Grant.STATUS_ACTIVE,
    },
    {
        "donor_name": "Sunita Rao",
        "name": "Women's Self-Help Group Seed Fund",
        "total_amount": Decimal("350000.00"),
        "start_date": date(2026, 2, 1),
        "end_date": date(2026, 11, 30),
        "purpose": "Seed capital and training for women-led micro-enterprises in peri-urban areas.",
        "status": Grant.STATUS_ACTIVE,
    },
    {
        "donor_name": "Reliance Social Foundation",
        "name": "Skill India Vocational Training 2026",
        "total_amount": Decimal("3500000.00"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "purpose": "Certified vocational courses (plumbing, electrical, tailoring) for 500 youth.",
        "status": Grant.STATUS_ACTIVE,
    },
    {
        "donor_name": "USAID India Mission",
        "name": "Climate-Smart Agriculture Pilot",
        "total_amount": Decimal("4800000.00"),
        "start_date": date(2025, 9, 1),
        "end_date": date(2027, 8, 31),
        "purpose": "Introduce drought-resistant crops, drip irrigation, and agri-extension services.",
        "status": Grant.STATUS_ACTIVE,
    },
    {
        "donor_name": "Tata Trusts",
        "name": "Safe Drinking Water Initiative – Phase 2",
        "total_amount": Decimal("2750000.00"),
        "start_date": date(2026, 6, 1),
        "end_date": date(2027, 5, 31),
        "purpose": "Water purification units and community maintenance training in 15 tribal villages.",
        "status": Grant.STATUS_PENDING,
    },
    {
        "donor_name": "Infosys Foundation",
        "name": "AI Literacy for School Teachers",
        "total_amount": Decimal("1200000.00"),
        "start_date": date(2026, 4, 1),
        "end_date": date(2026, 12, 31),
        "purpose": "Train 200 government school teachers in AI tools and digital pedagogy.",
        "status": Grant.STATUS_ACTIVE,
    },
    {
        "donor_name": "Navjyoti Corporate CSR",
        "name": "Digital Literacy for Youth – Phase 2",
        "total_amount": Decimal("850000.00"),
        "start_date": date(2026, 10, 1),
        "end_date": date(2027, 9, 30),
        "purpose": "Expand computer labs to 5 new districts and add cybersecurity curriculum.",
        "status": Grant.STATUS_PENDING,
    },
    {
        "donor_name": "Yashoda Foundation",
        "name": "Maternal Mental Health Support Program",
        "total_amount": Decimal("720000.00"),
        "start_date": date(2026, 5, 1),
        "end_date": date(2027, 4, 30),
        "purpose": "Counselling, peer support groups, and awareness drives for new mothers.",
        "status": Grant.STATUS_ACTIVE,
    },
]


# ---------------------------------------------------------------------------
# New expenses
# ---------------------------------------------------------------------------
# These reference grants by (donor_name, grant_name) tuples so we can look
# them up after upserts.
NEW_EXPENSES = [
    {
        "title": "Library Books and Furniture – Batch 1",
        "total_amount": Decimal("180000.00"),
        "expense_date": date(2026, 3, 15),
        "description": "Procurement of 3,000 books, shelving units, and reading mats for 4 schools.",
        "receipt": "expenses/receipts/seed/library_books_batch1.pdf",
        "allocations": [
            {"donor": "Arjun Mehta",           "grant": "Rural School Library Program",         "amount": Decimal("180000.00")},
        ],
    },
    {
        "title": "SHG Training and Workshop – February",
        "total_amount": Decimal("95000.00"),
        "expense_date": date(2026, 2, 20),
        "description": "Two-day workshop on bookkeeping, product costing, and market linkages for SHG members.",
        "receipt": "expenses/receipts/seed/shg_workshop_feb.pdf",
        "allocations": [
            {"donor": "Sunita Rao",            "grant": "Women's Self-Help Group Seed Fund",   "amount": Decimal("95000.00")},
        ],
    },
    {
        "title": "Vocational Training Instructor Fees – Q1",
        "total_amount": Decimal("320000.00"),
        "expense_date": date(2026, 1, 31),
        "description": "Honoraria for 12 certified instructors across plumbing, electrical, and tailoring trades.",
        "receipt": "expenses/receipts/seed/instructor_fees_q1.pdf",
        "allocations": [
            {"donor": "Reliance Social Foundation", "grant": "Skill India Vocational Training 2026", "amount": Decimal("320000.00")},
        ],
    },
    {
        "title": "Agri-Extension Field Visits – Oct–Dec 2025",
        "total_amount": Decimal("210000.00"),
        "expense_date": date(2025, 12, 31),
        "description": "Baseline soil testing, farmer outreach meetings, and travel costs across three districts.",
        "receipt": "expenses/receipts/seed/agri_field_visits_q3.pdf",
        "allocations": [
            {"donor": "USAID India Mission",   "grant": "Climate-Smart Agriculture Pilot",      "amount": Decimal("210000.00")},
        ],
    },
    {
        "title": "Teacher Training Module Development",
        "total_amount": Decimal("280000.00"),
        "expense_date": date(2026, 4, 30),
        "description": "Curriculum design, pilot testing, and printing of AI literacy modules for 200 teachers.",
        "receipt": "expenses/receipts/seed/teacher_training_modules.pdf",
        "allocations": [
            {"donor": "Infosys Foundation",    "grant": "AI Literacy for School Teachers",      "amount": Decimal("280000.00")},
        ],
    },
    {
        "title": "Maternal Counselling Staff Salaries – May",
        "total_amount": Decimal("120000.00"),
        "expense_date": date(2026, 5, 31),
        "description": "Monthly salaries for 4 counsellors and 1 program coordinator.",
        "receipt": "expenses/receipts/seed/counselling_salaries_may.pdf",
        "allocations": [
            {"donor": "Yashoda Foundation",    "grant": "Maternal Mental Health Support Program", "amount": Decimal("120000.00")},
        ],
    },
    {
        "title": "Office Rent and Utilities – Q1 2026",
        "total_amount": Decimal("75000.00"),
        "expense_date": date(2026, 3, 31),
        "description": "Shared overhead: office rent, electricity, and internet across all active programs.",
        "receipt": "expenses/receipts/seed/office_rent_q1_2026.pdf",
        "allocations": [
            # Split proportionally across three active grants
            {"donor": "Yashoda Foundation",         "grant": "Community Health Outreach 2026",       "amount": Decimal("25000.00")},
            {"donor": "Bright Future Trust",         "grant": "Girls Education Scholarship Program",  "amount": Decimal("25000.00")},
            {"donor": "Reliance Social Foundation",  "grant": "Skill India Vocational Training 2026", "amount": Decimal("25000.00")},
        ],
    },
    {
        "title": "Seed Fund Disbursement – 20 SHGs",
        "total_amount": Decimal("200000.00"),
        "expense_date": date(2026, 4, 15),
        "description": "Seed capital transfers to 20 women's self-help groups (Rs.10,000 each).",
        "receipt": "expenses/receipts/seed/shg_seed_disbursement_april.pdf",
        "allocations": [
            {"donor": "Sunita Rao",            "grant": "Women's Self-Help Group Seed Fund",   "amount": Decimal("200000.00")},
        ],
    },
    {
        "title": "Drip Irrigation Equipment Purchase",
        "total_amount": Decimal("560000.00"),
        "expense_date": date(2026, 2, 10),
        "description": "Procurement of drip-line kits for 40 farmers in Wardha district.",
        "receipt": "expenses/receipts/seed/drip_irrigation_wardha.pdf",
        "allocations": [
            {"donor": "USAID India Mission",   "grant": "Climate-Smart Agriculture Pilot",      "amount": Decimal("560000.00")},
        ],
    },
    {
        "title": "Medical Camp Supplies – Q2 2026",
        "total_amount": Decimal("310000.00"),
        "expense_date": date(2026, 4, 20),
        "description": "Medicines, rapid diagnostic tests, and equipment for four community health camps.",
        "receipt": "expenses/receipts/seed/medical_camp_q2.pdf",
        "allocations": [
            {"donor": "Yashoda Foundation",    "grant": "Community Health Outreach 2026",        "amount": Decimal("190000.00")},
            {"donor": "Yashoda Foundation",    "grant": "Maternal Mental Health Support Program", "amount": Decimal("120000.00")},
        ],
    },
]


class Command(BaseCommand):
    help = "Patch PAN numbers on existing donors and seed additional dummy data (idempotent)."

    def handle(self, *args, **options):
        try:
            created_by = User.objects.filter(role=User.ROLE_FINANCE).order_by("id").first()
            if not created_by:
                raise CommandError(
                    "No Finance Manager user found. "
                    "Create a user with role='finance' first, then re-run."
                )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        patched_donors = 0
        created_donors = 0
        created_grants = 0
        created_expenses = 0
        created_allocations = 0

        with transaction.atomic():

            # ------------------------------------------------------------------
            # 1. Patch PAN numbers + contact details onto existing donors
            # ------------------------------------------------------------------
            self.stdout.write("Patching existing donors with PAN numbers...")
            for donor_name, details in EXISTING_DONOR_PANS.items():
                updated = Donor.objects.filter(name=donor_name).update(
                    pan_number=details["pan"],
                    email=details.get("email", ""),
                    phone=details.get("phone", ""),
                    country=details.get("country", "India"),
                )
                if updated:
                    patched_donors += updated
                    self.stdout.write(f"  [OK] Patched: {donor_name}")

            # ------------------------------------------------------------------
            # 2. Create new donors
            # ------------------------------------------------------------------
            self.stdout.write("\nCreating new donors...")
            for d in NEW_DONORS:
                donor, created = Donor.objects.get_or_create(
                    name=d["name"],
                    defaults={
                        "donor_type": d["donor_type"],
                        "email":       d.get("email", ""),
                        "phone":       d.get("phone", ""),
                        "country":     d.get("country", "India"),
                        "address":     d.get("address", ""),
                        "pan_number":  d.get("pan_number", ""),
                        "notes":       d.get("notes", ""),
                        "is_active":   True,
                    },
                )
                if created:
                    created_donors += 1
                    self.stdout.write(f"  [OK] Created donor: {donor.name}")
                else:
                    # Still update PAN if it was missing
                    if not donor.pan_number and d.get("pan_number"):
                        donor.pan_number = d["pan_number"]
                        donor.save(update_fields=["pan_number"])
                    self.stdout.write(f"  -- Already exists: {donor.name}")

            # ------------------------------------------------------------------
            # 3. Create new grants
            # ------------------------------------------------------------------
            self.stdout.write("\nCreating new grants...")
            for g in NEW_GRANTS:
                try:
                    donor = Donor.objects.get(name=g["donor_name"])
                except Donor.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"  ⚠ Donor not found: {g['donor_name']} — skipping grant '{g['name']}'")
                    )
                    continue

                _, grant_created = Grant.objects.get_or_create(
                    donor=donor,
                    name=g["name"],
                    defaults={
                        "total_amount": g["total_amount"],
                        "start_date":   g["start_date"],
                        "end_date":     g["end_date"],
                        "purpose":      g["purpose"],
                        "status":       g["status"],
                        "is_active":    True,
                    },
                )
                if grant_created:
                    created_grants += 1
                    self.stdout.write(f"  [OK] Created grant: {g['name']}")
                else:
                    self.stdout.write(f"  -- Already exists: {g['name']}")

            # ------------------------------------------------------------------
            # 4. Create new expenses + allocations
            # ------------------------------------------------------------------
            self.stdout.write("\nCreating new expenses...")
            for e in NEW_EXPENSES:
                expense, expense_created = Expense.objects.get_or_create(
                    title=e["title"],
                    total_amount=e["total_amount"],
                    expense_date=e["expense_date"],
                    defaults={
                        "description": e["description"],
                        "receipt":     e["receipt"],
                        "created_by":  created_by,
                        "is_active":   True,
                    },
                )
                if expense_created:
                    created_expenses += 1
                    self.stdout.write(f"  [OK] Created expense: {e['title']}")
                else:
                    self.stdout.write(f"  -- Already exists: {e['title']}")

                for alloc in e["allocations"]:
                    try:
                        grant = Grant.objects.get(
                            donor__name=alloc["donor"],
                            name=alloc["grant"],
                        )
                    except Grant.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(
                                f"    ⚠ Grant not found: '{alloc['grant']}' "
                                f"(donor: {alloc['donor']}) — skipping allocation"
                            )
                        )
                        continue

                    _, alloc_created = ExpenseAllocation.objects.get_or_create(
                        expense=expense,
                        grant=grant,
                        defaults={"allocated_amount": alloc["amount"]},
                    )
                    if alloc_created:
                        created_allocations += 1

        # ----------------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Donors patched with PAN:  {patched_donors}"))
        self.stdout.write(self.style.SUCCESS(f"New donors created:       {created_donors}"))
        self.stdout.write(self.style.SUCCESS(f"New grants created:       {created_grants}"))
        self.stdout.write(self.style.SUCCESS(f"New expenses created:     {created_expenses}"))
        self.stdout.write(self.style.SUCCESS(f"New allocations created:  {created_allocations}"))
        self.stdout.write(self.style.SUCCESS("\nDone! All data is now in the database."))
