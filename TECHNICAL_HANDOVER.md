# PaperTrail: Technical Deep Dive & Handover Document

**Project:** PaperTrail NGO Management System  
**Framework:** Django 5.2  
**Database:** PostgreSQL (production) / SQLite (development)  
**Async:** Celery + Redis  
**Frontend:** Bootstrap 5 + Django Templates  

---

## TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [Data Architecture Deep Dive](#data-architecture-deep-dive)
3. [Request-Response Lifecycle](#request-response-lifecycle)
4. [Logic & Patterns](#logic--patterns)
5. [Hidden Plumbing (Settings & Utils)](#hidden-plumbing-settings--utils)
6. [Security & Performance](#security--performance)
7. [File-by-File Breakdown](#file-by-file-breakdown)
8. [Common Workflows](#common-workflows)
9. [Interview Talking Points](#interview-talking-points)

---

## ARCHITECTURE OVERVIEW

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────┐
│                     User Browser                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/HTTPS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Django Request Pipeline                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Middleware (CSRF, Auth, AuditMiddlewareUser, etc)   │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              URL Router (urls.py)                            │
│  Dispatches to app-specific URLconf                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              View Layer (FBVs with Decorators)              │
│  - Permission checks via @role_required, @finance_required  │
│  - Form validation & processing                             │
│  - Signal triggering for audit logging                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────┴──────┬──────────┐
                    ▼             ▼          ▼
         ┌──────────────────┐  ┌────────┐ ┌────────────┐
         │  Django ORM      │  │Signals │ │  Celery   │
         │  (Model Query)   │  │ (Audit)│ │  (Async)  │
         └────────┬─────────┘  └────────┘ └────────────┘
                  │                            │
                  ▼                            ▼
    ┌───────────────────────────┐  ┌──────────────────────┐
    │ PostgreSQL/SQLite DB      │  │  Redis (Task Queue)  │
    │ (persists data)           │  │  (async jobs)        │
    └───────────────────────────┘  └──────────────────────┘
                  │
         ┌────────┴────────┐
         ▼                 ▼
    ┌─────────────┐   ┌──────────────┐
    │ AuditLog    │   │ File Storage │
    │ (immutable) │   │ (media/)     │
    └─────────────┘   └──────────────┘
                           │
                           ▼
    ┌──────────────────────────────────┐
    │ Rendered Template                │
    │ (base.html + app templates)      │
    └──────────────────────────────────┘
                           │
                           ▼
                    ┌────────────────┐
                    │  User Browser   │
                    └────────────────┘
```

### Project Apps & Responsibilities

```
apps/
├── accounts/           → User authentication + role-based access control
├── compliance/         → Certificate tracking (FCRA, 80G, 12A) + alerts
├── expense/            → Expense records + grant allocations
├── donors/             → Donor registry + contact info
├── grants/             → Grant management + budget tracking
├── reports/            → PDF/Excel report generation
└── audit/              → Immutable audit logging + trail
```

---

## DATA ARCHITECTURE DEEP DIVE

### 1. **User Model** (`apps/accounts/models.py`)

```python
class User(AbstractUser):
    ROLE_CHOICES = [ADMIN, FINANCE, AUDITOR]
    role = CharField(choices=ROLE_CHOICES, default=ROLE_AUDITOR)
    phone = CharField(max_length=20, blank=True)
```

**Why this design?**
- **AbstractUser inheritance:** Extends Django's built-in User with custom fields while maintaining all authentication machinery (password hashing, is_active, last_login, etc).
- **Role-based access:** The `role` field drives all authorization (see @role_required decorator). Three tiers: Admin (full permissions) → Finance (create/edit financials) → Auditor (read-only reports).
- **Data integrity:** Using choices restricts roles to exact values (no arbitrary strings).

**Relationships:**
- One-to-Many with AuditLog (`related_name="audit_logs"`) — tracks WHO changed WHAT
- One-to-Many with ComplianceDocument, Expense — tracks WHO uploaded/created

**Key properties:**
```python
@property
def can_write(self):
    return self.role == self.ROLE_FINANCE
```
This checks write permission in form validation (see compliance gate in `ExpenseForm`).

---

### 2. **ComplianceDocument Model** (`apps/compliance/models.py`)

```python
class ComplianceDocument(models.Model):
    CERT_TYPE_CHOICES = [(FCRA, "FCRA"), (G80, "80G"), (A12, "12A")]
    
    cert_type = CharField(unique=True, choices=CERT_TYPE_CHOICES)
    issue_date = DateField()
    expiry_date = DateField()
    certificate_file = FileField(upload_to="compliance/")
    uploaded_by = ForeignKey(User, on_delete=models.SET_NULL, null=True)
    yellow_alert_sent = DateTimeField(null=True, blank=True)
```

**Why this design?**

- **Unique cert_type:** Only ONE of each certificate type can exist (business rule for NGO compliance).
- **uploaded_by = ForeignKey(..., null=True):** If the user who uploaded is deleted, keep the record (audit trail still matters). `on_delete=models.SET_NULL` ensures data integrity.
- **FileField with upload_to="compliance/":** Auto-organizes uploads into `media/compliance/` (prevents filename collisions, groups related files).
- **yellow_alert_sent tracking:** Prevents duplicate alert emails. Celery task marks this field after sending (idempotency).

**Status Properties (Computed, NOT stored):**
```python
@property
def status(self):
    today = timezone.localdate()
    if self.expiry_date < today:        return "red"      # Expired
    if (self.expiry_date - today).days <= 180: return "yellow"  # Expiring soon
    return "green"  # Valid
```
**Why computed?** The status changes daily—storing it would require daily batch updates. Computing on-demand is cleaner. Uses `@property` (no DB query overhead since dates are already loaded).

**Compliance Gate Logic:**
```python
def is_compliant():
    """All 3 certs must exist and none expired (red)"""
    required = {FCRA, G80, A12}
    found = {d.cert_type: d for d in ComplianceDocument.objects.all()}
    if not required.issubset(found.keys()):
        return False
    return all(doc.status != "red" for doc in found.values())
```
This blocks expense/grant creation until compliance is met (gating logic in views).

---

### 3. **Donor Model** (`apps/donors/models.py`)

```python
class Donor(models.Model):
    TYPE_CHOICES = [INDIVIDUAL, ORGANIZATION, GOVERNMENT, CORPORATE]
    
    name = CharField(max_length=200)
    donor_type = CharField(choices=TYPE_CHOICES, default=INDIVIDUAL)
    email = EmailField(blank=True)
    phone = CharField(blank=True)
    pan_number = CharField(blank=True)
    is_active = BooleanField(default=True)  # Soft delete
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**Why this design?**

- **Soft delete pattern (`is_active`):** Never delete donors (audit trail loss). Instead, mark inactive. Queries filter `is_active=True` by default.
- **blank=True on contact fields:** Not all donors have email/phone (e.g., govt agencies use registered addresses).
- **auto_now_add / auto_now:** `auto_now_add=True` sets `created_at` once on creation (can't be changed). `auto_now=True` updates `updated_at` every save (tracks last mod time). Useful for audit.
- **pan_number for India:** NGOs need this for tax compliance.

**Relationship to Grant:**
- One Donor → Many Grants (`related_name="grants"`)
- If we try to delete a donor, the `on_delete=models.PROTECT` on Grant.donor prevents it (data integrity).

---

### 4. **Grant Model** (`apps/grants/models.py`) — **MOST COMPLEX**

```python
class Grant(models.Model):
    STATUS_CHOICES = [PENDING, ACTIVE, CLOSED]
    
    donor = ForeignKey(Donor, on_delete=models.PROTECT, related_name="grants")
    name = CharField(max_length=250)
    total_amount = DecimalField(max_digits=14, decimal_places=2)
    start_date = DateField()
    end_date = DateField()
    status = CharField(choices=STATUS_CHOICES, default=PENDING)
    is_active = BooleanField(default=True)  # Soft delete
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**Why this design?**

- **Decimal(14, 2) for money:** Never use FloatingPoint for currency (rounding errors). Decimal is exact. 14 digits = ₹99,999,999.99 (plenty for NGO budgets).
- **start_date / end_date validation:** Enforced at form level (`ExpenseForm` checks expense_date is within grant period). This prevents expenses being allocated to grants they shouldn't be.
- **on_delete=models.PROTECT on donor FK:** If you try to delete a donor with grants, Django raises IntegrityError (prevents orphaned records).

**Computed Properties (These are KEY):**

```python
@property
def utilized_amount(self):
    """Sum all active allocations to this grant"""
    result = self.allocations.filter(
        expense__is_active=True
    ).aggregate(total=Sum("allocated_amount"))
    return result["total"] or 0

@property
def remaining_amount(self):
    return self.total_amount - self.utilized_amount

@property
def burn_rate(self):
    """Percentage of grant used"""
    if self.total_amount == 0:
        return 0
    return round((self.utilized_amount / self.total_amount) * 100, 1)
```

**Why computed?**
- These must update in real-time as expenses are added/removed.
- Storing them creates data sync issues (need batch jobs to keep them fresh).
- Computing on-demand is immediate + accurate.
- Performance: Uses `aggregate(Sum(...))` which is a single SQL SUM() query (very fast).

---

### 5. **Expense & ExpenseAllocation Models** (`apps/expenses/models.py`) — **THE STAR**

```python
class Expense(models.Model):
    title = CharField(max_length=300)
    total_amount = DecimalField(max_digits=14, decimal_places=2)
    expense_date = DateField()
    receipt = FileField(upload_to="expenses/receipts/")  # Required (enforced at form)
    created_by = ForeignKey(User, on_delete=models.PROTECT)
    is_active = BooleanField(default=True)  # Soft delete
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**The Allocation Pattern (Many-to-Many through explicit model):**

```python
class ExpenseAllocation(models.Model):
    expense = ForeignKey(Expense, on_delete=models.CASCADE, related_name="allocations")
    grant = ForeignKey(Grant, on_delete=models.PROTECT, related_name="allocations")
    allocated_amount = DecimalField(max_digits=14, decimal_places=2)
    
    class Meta:
        unique_together = [("expense", "grant")]  # One allocation per expense-grant pair
```

**Why this design (the "through" pattern)?**

You have: **1 Expense** → can map to **Many Grants** (split across funding sources).

Example:
```
Expense: "Office rent ₹50,000"
├─ Grant A (humanitarian): ₹30,000
├─ Grant B (education): ₹15,000
└─ Grant C (other): ₹5,000
Total: ₹50,000 ✓
```

This is NOT a ManyToMany field; it's a **ForeignKey to a through table** because:
1. You need the `allocated_amount` on the relationship itself.
2. You need to validate: sum of all allocations = expense total.
3. You need to ensure allocations don't exceed grant budgets.

**on_delete logic:**
- `expense ... on_delete=models.CASCADE`: If expense is deleted, its allocations are too (makes sense—orphaned allocations are useless).
- `grant ... on_delete=models.PROTECT`: If grant is deleted, allocations prevent it (data integrity—grants with spending can't vanish).

**unique_together constraint:**
- Prevents duplicate allocations to the same grant.
- Example: Can't accidentally allocate the same expense to "Grant A" twice.

---

### 6. **AuditLog Model** (`apps/audit/models.py`) — **IMMUTABLE TRUST LOG**

```python
class AuditLog(models.Model):
    ACTION_CHOICES = [(CREATED, "Created"), (UPDATED, "Updated"), (DELETED, "Deleted")]
    
    action = CharField(choices=ACTION_CHOICES)
    content_type = ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = PositiveIntegerField()
    object_repr = CharField(max_length=255)
    
    changed_by = ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = DateTimeField(auto_now_add=True, db_index=True)
    
    changes = JSONField(
        default=dict,
        help_text="{'field': {'old': old_val, 'new': new_val}}"
    )
    
    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["changed_by", "-timestamp"]),
        ]
```

**Why this design?**

The **GenericForeignKey pattern** (via ContentType):
- Instead of separate audit tables for each model, one table tracks changes to Expense, Grant, ComplianceDocument, etc.
- `content_type` + `object_id` form a pointer to ANY model instance.
- `object_repr` caches the string representation ("Grant ABC from Donor XYZ") so you can read logs even if the object is deleted.

**Immutability enforced:**
- `auto_now_add=True` on timestamp (can't be spoofed).
- No `update_fields` allowed on AuditLog (only insert).
- `on_delete=models.PROTECT` on content_type (prevents deletion).

**JSONField for changes:**
```python
{
    "total_amount": {"old": "50000.00", "new": "60000.00"},
    "status": {"old": "pending", "new": "active"}
}
```
This captures before/after, enabling detailed compliance reports.

**Indexes:**
```python
models.Index(fields=["content_type", "object_id"])  # Query: "All changes to this Grant"
models.Index(fields=["changed_by", "-timestamp"])   # Query: "All changes by this User"
```
These speed up common audit queries (no full table scans).

---

### Data Relationship Summary

```
User
├── (1:N) ComplianceDocument.uploaded_by
├── (1:N) Expense.created_by
├── (1:N) AuditLog.changed_by
└── (1:N) Grant (implicit, via audit)

Donor
└── (1:N) Grant.donor

Grant
├── (1:N) ExpenseAllocation.grant
└── (1:N) AuditLog (via ContentType)

Expense
├── (1:N) ExpenseAllocation.expense  ← Reverse: expense.allocations
└── (1:N) AuditLog (via ContentType)

ExpenseAllocation
├── (N:1) Expense
└── (N:1) Grant
```

**Critical Constraints:**
```
User on_delete=PROTECT          → Can't delete users with active expenses
Donor on_delete=PROTECT          → Can't delete donors with active grants
Grant.donor on_delete=PROTECT    → Donor can't be deleted if grants exist
Expense on_delete=CASCADE        → Delete expense = delete allocations
ExpenseAllocation.grant on_delete=PROTECT  → Grant can't be deleted if allocations exist
```

---

## REQUEST-RESPONSE LIFECYCLE

### Most Complex Feature: Expense Creation with Inline Allocations

This demonstrates the full request-response flow:

```
Step 1: User visits /expenses/create/
  ▼
Step 2: expense_create() GET handler
  - Creates empty ExpenseForm
  - Creates empty AllocationFormSet (extra=1 blank row)
  - Renders form + formset to template
  ▼
Step 3: Template renders (expense_form.html)
  - Form fields: title, total_amount, expense_date, description, receipt
  - Formset fields: Multiple rows of { grant, allocated_amount }
  - Hidden CSRF token injected by response
  ▼
Step 4: User fills form + formset, hits "Submit"
  - Expense form fields filled
  - Allocation rows filled (e.g., "Grant A: ₹30,000" + "Grant B: ₹20,000")
  ▼
Step 5: Browser POST to /expenses/create/
  - CSRF middleware validates token (Django auto-check)
  - Request reaches expense_create() POST handler
  ▼
Step 6: expense_create() POST handler processes request

    form = ExpenseForm(request.POST or None, request.FILES or None)
    formset = AllocationFormSet(request.POST or None, prefix="allocations")

  - ExpenseForm.clean_receipt() → Validates receipt file exists
  - ExpenseForm.clean() → Calls is_compliant() (compliance gate)
    If compliance check fails:
      ✗ Stop here, return to form with error messages
      ✗ No DB write
  - AllocationFormSet.is_valid() → Each row validates:
    - grant field exists in active grants
    - allocated_amount is numeric
  ▼
Step 7: Manual validation: _validate_allocations(expense, formset)
  
    Checks:
    1. Sum of all allocations == expense.total_amount
       ✗ If "Grant A: ₹30k + Grant B: ₹15k" but expense is ₹50k → Error
    2. expense_date is within each grant's period (start_date - end_date)
       ✗ If expense is dated 2023-01-01 but grant is 2024-01-01→2024-12-31 → Error
    3. Grant budget not exceeded
       ✗ If Grant already has ₹40k allocated and you try to add ₹20k more, 
         but grant is only ₹50k total → Error

    All validations pass?
      ✓ Proceed to DB write
      ✗ If any fail, return form with error messages

  ▼
Step 8: Atomic database transaction

    with transaction.atomic():
        expense.created_by = request.user
        expense.save()  ← Creates Expense record
        
          SIGNAL TRIGGERED: pre_save(Expense)
            → Signal handler: capture_expense_old_state()
            → No old instance (new record), stores None
        
          SIGNAL TRIGGERED: post_save(Expense, created=True)
            → Signal handler: log_expense_change(created=True)
            → AuditLog.log_action(ACTION_CREATED, instance=expense, ...)
            → New AuditLog created with:
              - action: "created"
              - object_repr: "Office Rent – ₹50000 (2024-01-15)"
              - changed_by: request.user
              - changes: {}
              - timestamp: timezone.now()
        
        formset.instance = expense  ← Attach expense to formset
        formset.save()  ← Creates all ExpenseAllocation records
        
          For each allocation in formset:
            SIGNAL TRIGGERED: post_save(ExpenseAllocation, created=True)
              → AuditLog entry created for each allocation

    If ANY exception occurs (e.g., DB constraint violation):
      ✗ ROLLBACK all inserts → No partial data in DB

  ▼
Step 9: Redirect & messaging

    messages.success(request, "Expense recorded successfully.")
    return redirect("expenses:expense_detail", pk=expense.pk)

  ▼
Step 10: User sees success message and expense detail page
```

### Template Context Flow

#### View Renders Context:

```python
@login_required
@finance_required
def expense_create(request):
    form = ExpenseForm(...)
    formset = AllocationFormSet(...)
    
    context = {
        "form": form,
        "formset": formset,
        "title": "Record Expense",
        "alloc_errors": alloc_errors,
    }
    return render(request, "expenses/expense_form.html", context)
```

#### Template Uses Context:

```html
<!-- expenses/expense_form.html -->
{% extends "base.html" %}

{% block title %}{{ title }}{% endblock %}

{% block content %}
<h1>{{ title }}</h1>

<!-- Main form -->
<form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    
    <!-- Renders all form fields with Bootstrap styling -->
    {{ form|crispy }}
    
    <!-- Renders formset (multiple allocation rows) -->
    {{ formset.management_form }}  <!-- Hidden fields: TOTAL_FORMS, INITIAL_FORMS, etc -->
    
    {% for allocation_form in formset %}
        <div class="card">
            {{ allocation_form|crispy }}
        </div>
    {% endfor %}
    
    <!-- Display any allocation errors -->
    {% if alloc_errors %}
        {% for error in alloc_errors %}
            <div class="alert alert-danger">{{ error }}</div>
        {% endfor %}
    {% endif %}
    
    <button type="submit" class="btn btn-primary">Save Expense</button>
</form>
{% endblock %}
```

**How the template renders context:**
1. `{{ title }}` → "Record Expense" (interpolated into HTML)
2. `{{ form|crispy }}` → Django Crispy Forms filter converts form fields to Bootstrap, including all validation errors
3. `{% csrf_token %}` → Security token preventing CSRF attacks
4. `{{ formset.management_form }}` → Hidden fields (Expense allocation count, etc)
5. `{% for allocation_form in formset %}` → Loop over formset rows
6. Template auto-escapes all variables (XSS protection)

---

## LOGIC & PATTERNS

### 1. Function-Based Views (FBVs) vs Class-Based Views (CBVs)

**This project uses FBVs exclusively.** Here's why:

#### FBV Approach (What we're using):
```python
@login_required
@role_required("admin")
def user_list(request):
    users = User.objects.all().order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})
```

**Pros:**
- ✓ **Simple and explicit:** Linear code flow (read top to bottom).
- ✓ **Flexible decorators:** Stack `@login_required`, `@role_required`, `@finance_required` in any order.
- ✓ **Easy to debug:** No inheritance chains or metaclasses (CBV uses complex MRO).
- ✓ **Less boilerplate:** No need to inherit from generic views.

**Cons:**
- ✗ **Decorator stacking:** With 5+ decorators, readability suffers.
- ✗ **Code duplication:** Similar CRUD patterns repeat (list, create, edit, delete).
- ✗ **No built-in pagination:** Must implement manually if needed.

#### CBV Alternative (What we're NOT using):
```python
from django.views.generic import ListView

class UserListView(LoginRequiredMixin, UserRoleRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"

# urls.py
path("users/", UserListView.as_view(), name="user_list")
```

**Pros:**
- ✓ DRY (Don't Repeat Yourself) for standard CRUD.
- ✓ Built-in pagination, filtering, ordering.
- ✓ Mixins enforce consistency.

**Cons:**
- ✗ **Magic behavior:** Mixins can override methods secretly (hard to trace).
- ✗ **Steep learning curve:** Requires understanding MRO, `get_context_data()`, `get_queryset()`.
- ✗ **Over-engineered for simple views:** E.g., a 1-line permission check becomes a 10-line mixin.

**Decision: FBVs for clarity** in a "vibe coding" project that prioritized moving fast. If this grows to 50+ views, consider CBVs.

---

### 2. Custom Decorator Pattern: `@role_required`

#### How it works:

```python
# apps/accounts/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def role_required(*roles):
    """Restrict view to users whose role is in the given list."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, "You do not have permission...")
                return redirect("accounts:dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
```

#### Usage:

```python
@login_required                          # First: ensure authenticated
@role_required("admin", "finance")       # Then: ensure role is admin OR finance
def grant_create(request):
    ...
```

#### Execution Flow (Decorator Stacking):

```
Request arrives
  ↓
login_required checks: Is user logged in?
  ├─ NO → Redirect to /accounts/login/
  └─ YES → Pass to next decorator
  ↓
role_required checks: Is user.role in ("admin", "finance")?
  ├─ NO → Show error, redirect to dashboard
  └─ YES → Pass to view function
  ↓
grant_create(request) executes
```

**Why this pattern?**
- ✓ **Reusable:** `@role_required` applies to any view.
- ✓ **Declarative:** Permissions are explicit at the top (easy to audit).
- ✓ **Clean separation:** Authentication logic is separate from business logic.

**Why not class-based?**
```python
# CBV approach (verbose)
class GrantCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    allowed_roles = ["admin", "finance"]
    model = Grant
    form_class = GrantForm

# FBV approach (readable)
@login_required
@role_required("admin", "finance")
def grant_create(request):
    ...
```

---

### 3. Form Validation Deep Dive

#### Single-Field Validation:

```python
# apps/compliance/forms.py
class ComplianceDocumentForm(forms.ModelForm):
    def clean_certificate_file(self):
        """Validate individual field"""
        file = self.cleaned_data.get("certificate_file")
        if file and file.size > 10 * 1024 * 1024:  # 10MB
            raise ValidationError("File too large")
        return file
```

**When it runs:** After form is bound (POST received), before `form.is_valid()` returns True. Each `clean_<fieldname>()` is called in sequence.

#### Cross-Field Validation:

```python
# apps/compliance/forms.py
class ComplianceDocumentForm(forms.ModelForm):
    def clean(self):
        """Validate across multiple fields"""
        cleaned = super().clean()
        issue = cleaned.get("issue_date")
        expiry = cleaned.get("expiry_date")
        
        if issue and expiry and expiry <= issue:
            raise ValidationError("Expiry must be after issue date.")
        return cleaned
```

**When it runs:** After ALL field-level `clean_<field>()` methods. All cleaned data is available here.

#### Complex Validation: Compliance Gate

```python
# apps/expenses/forms.py
class ExpenseForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        if not is_compliant():
            issues = get_compliance_issues()
            raise ValidationError(f"Compliance gate failed: {issues}")
        return cleaned
```

**Why check in form?** Prevents non-compliant expenses from even being attempted. Form validation runs before view logic, so it's our first defense.

**The validation chain:**
```
form = ExpenseForm(request.POST)
  ├─ ExpenseForm.clean_receipt()
  │   ├─ Ensure receipt file exists
  │   └─ Return cleaned_data["receipt"]
  │
  ├─ ExpenseForm.clean()
  │   ├─ Call is_compliant()
  │   │   ├─ Check FCRA exists and not red
  │   │   ├─ Check 80G exists and not red
  │   │   ├─ Check 12A exists and not red
  │   │   └─ Return True if all pass
  │   └─ Raise ValidationError if not_compliant
  │
  └─ form.is_valid()
      └─ Returns True only if NO errors in any clean() method
```

---

### 4. Formset Validation: Main Form + Inline Many

#### Setup:

```python
# apps/expenses/forms.py
AllocationFormSet = inlineformset_factory(
    Expense,                    # Parent model
    ExpenseAllocation,          # Child model
    form=ExpenseAllocationForm,
    extra=1,                    # Show 1 blank row by default
    min_num=1,                  # At least 1 allocation required
    validate_min=True,
    can_delete=True,            # Allow unchecking rows to delete
)
```

#### Processing:

```python
@login_required
@finance_required
def expense_create(request):
    form = ExpenseForm(request.POST or None, request.FILES or None)
    formset = AllocationFormSet(request.POST or None, prefix="allocations")
    
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():  # BOTH must be valid
            expense = form.save(commit=False)  # Create but don't save yet
            
            # Custom cross-formset validation
            alloc_errors = _validate_allocations(expense, formset)
            if alloc_errors:
                # Re-populate form and show errors
                for err in alloc_errors:
                    messages.error(request, err)
            else:
                with transaction.atomic():
                    expense.created_by = request.user
                    expense.save()
                    formset.instance = expense  # Attach parent
                    formset.save()
                return redirect(...)
    
    return render(request, "expenses/expense_form.html", {
        "form": form,
        "formset": formset,
    })
```

**The `_validate_allocations()` function:**

```python
def _validate_allocations(expense, formset):
    """Cross-formset validation: allocations must sum to expense total"""
    errors = []
    total = Decimal("0")
    
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue  # Skip deleted rows
        
        grant = form.cleaned_data.get("grant")
        amount = form.cleaned_data.get("allocated_amount", Decimal("0"))
        total += amount
        
        # Rule 1: Expense date must be within grant period
        if grant and expense.expense_date:
            if not (grant.start_date <= expense.expense_date <= grant.end_date):
                errors.append(
                    f"Expense date {expense.expense_date} is outside "
                    f"'{grant.name}' period ({grant.start_date}–{grant.end_date})."
                )
        
        # Rule 2: Grant budget must not be exceeded
        existing_alloc = ExpenseAllocation.objects.filter(
            grant=grant, expense__is_active=True
        ).exclude(
            expense=expense  # Exclude current being edited
        ).aggregate(Sum("allocated_amount"))["used"] or Decimal("0")
        
        if existing_alloc + amount > grant.total_amount:
            errors.append(
                f"Allocation of ₹{amount} exceeds available budget "
                f"(₹{grant.total_amount - existing_alloc} remaining)."
            )
    
    # Rule 3: Sum of allocations must equal expense total
    if total != expense.total_amount:
        errors.append(
            f"Sum of allocations (₹{total}) must equal expense total (₹{expense.total_amount})."
        )
    
    return errors
```

**Why not use FormSet validation?** 
- Django FormSet has no built-in way to access parent form data.
- We need expense.total_amount to validate allocation sum.
- Solution: Custom validation function called in view after both forms validate.

---

## HIDDEN PLUMBING (Settings & Utils)

### 1. Settings Configuration (`papertrail/settings.py`)

#### INSTALLED_APPS (The Magic Order):

```python
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",          # Required for AuditLog ContentType
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Third-party
    "crispy_forms",                         # Bootstrap form styling
    "crispy_bootstrap5",                    # Bootstrap 5 styles
    
    # Project apps (OUR CODE)
    "apps.accounts",                        # Must be before model usage
    "apps.audit",
    "apps.compliance",
    "apps.donors",
    "apps.grants",
    "apps.expenses",
    "apps.reports",
    
    # Async
    "django_celery_beat",                   # Scheduled tasks
    "django_celery_results",                # Store task results
]
```

**Why this order matters:**
- `contenttypes` must come BEFORE any apps that use it (AuditLog uses ContentType).
- Project apps must come AFTER Django core (Django initializes ORM first).
- Celery apps last (don't block startup if Redis is down).

#### Middleware Stack (`MIDDLEWARE`):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",     # Enforces HTTPS, disables insecure headers
    "django.contrib.sessions.middleware.SessionMiddleware",  # Manages session cookies
    "django.middleware.common.CommonMiddleware",           # Handles URL rewriting
    "django.middleware.csrf.CsrfViewMiddleware",          # **CSRF PROTECTION** ← Crucial
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # Sets request.user
    "django.contrib.messages.middleware.MessageMiddleware",   # Flash messages (success/error)
    "django.middleware.clickjacking.XFrameOptionsMiddleware", # **XSS PROTECTION**
    "apps.audit.signals.AuditMiddlewareUser",             # **CUSTOM** Sets current user in thread-local
]
```

**Why AuditMiddlewareUser matters:**
```python
class AuditMiddlewareUser:
    """Capture user before view executes to track audit logs"""
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        set_current_user(request.user if request.user.is_authenticated else None)
        response = self.get_response(request)
        set_current_user(None)
        return response
```

When a signal fires (post_save), it calls `get_current_user()` to know WHO made the change. Without this middleware, audit logs would show `changed_by=None`.

#### Authentication (`AUTH_USER_MODEL`):

```python
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
```

**Custom User Model:** By setting `AUTH_USER_MODEL`, Django uses our User model everywhere (admin, sessions, signals). Migrations must reference it correctly.

#### Database:

```python
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}
```

**How it works:**
- `env.db()` reads `DATABASE_URL` from `.env` file.
- Example: `DATABASE_URL=postgresql://user:pass@localhost/papertrail`
- Falls back to SQLite if not set (local dev).

#### Celery Configuration:

```python
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"  # Store task results in DB
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE  # "Asia/Kolkata"

CELERY_BEAT_SCHEDULE = {
    "send-compliance-alerts-daily": {
        "task": "apps.compliance.tasks.send_compliance_alerts",
        "schedule": crontab(hour=6, minute=0),  # Daily at 6 AM
    },
}
```

**Why this setup?**
- **Redis as broker:** Fast in-memory queue (Celery pushes tasks here, workers pull them).
- **Django-DB as result backend:** Task results persist in DB (survives worker restarts).
- **JSON serialization:** Safe, language-agnostic format (not pickle which has security issues).
- **Celery Beat:** Runs scheduled tasks (like cron jobs but inside Django).

---

### 2. Utility Functions: Compliance Gate

#### `is_compliant()` (apps/compliance/utils.py):

```python
def is_compliant():
    """
    Returns True ONLY if:
    1. All three required certificates exist (FCRA, 80G, 12A)
    2. None of them are in "red" (expired) status
    """
    required = {ComplianceDocument.FCRA, ComplianceDocument.G80, ComplianceDocument.A12}
    docs = ComplianceDocument.objects.all()
    found = {d.cert_type: d for d in docs}
    
    # Check all required types exist
    if not required.issubset(found.keys()):
        return False
    
    # Check none are expired
    return all(doc.status != "red" for doc in found.values())
```

**Usage in views:**
```python
@login_required
@finance_required
def grant_create(request):
    if not is_compliant():
        issues = get_compliance_issues()
        messages.error(request, f"Compliance gate blocked: {issues}")
        return redirect("grants:grant_list")
    # ... rest of view
```

**Why this pattern?**
- **Centralized logic:** All compliance checks flow through one function (DRY).
- **Easy to test:** `is_compliant()` is a pure function (no side effects).
- **Used in forms + views:** Both form validation and views can call it.

#### `get_compliance_issues()` (apps/compliance/utils.py):

```python
def get_compliance_issues():
    """Return human-readable list of what's wrong"""
    required = {ComplianceDocument.FCRA, ComplianceDocument.G80, ComplianceDocument.A12}
    docs = ComplianceDocument.objects.all()
    found = {d.cert_type: d for d in docs}
    issues = []
    
    for cert_type in required:
        if cert_type not in found:
            label = dict(ComplianceDocument.CERT_TYPE_CHOICES).get(cert_type)
            issues.append(f"{label} is missing.")
        elif found[cert_type].status == "red":
            issues.append(f"{found[cert_type]} has expired.")
    
    return issues
```

**Example output:**
```python
>>> get_compliance_issues()
["FCRA Certificate is missing.", "80G Certificate has expired."]
```

---

### 3. Celery Tasks: Async Compliance Alerts

#### Setup (`papertrail/celery.py`):

```python
app = Celery("papertrail")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()  # Auto-loads tasks.py from all apps
```

#### Task Definition (`apps/compliance/tasks.py`):

```python
@shared_task(bind=True)
def send_yellow_alert_email_task(self, doc_id: int) -> bool:
    """
    Send email for ONE document expiring soon.
    Retries with exponential backoff if email fails.
    """
    try:
        doc = ComplianceDocument.objects.get(id=doc_id)
    except ComplianceDocument.DoesNotExist:
        return False
    
    admins = User.objects.filter(role="admin")
    admin_emails = [a.email for a in admins if a.email]
    
    if not admin_emails:
        return False
    
    subject = f"Certificate Alert: {doc.get_cert_type_display()} Expiring Soon"
    context = {"document": doc, "days_to_expiry": doc.days_to_expiry}
    
    try:
        message = render_to_string("compliance/notification_email.html", context)
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, admin_emails, html_message=message)
        
        # Mark as sent (prevents duplicate alerts)
        doc.yellow_alert_sent = timezone.now()
        doc.save(update_fields=["yellow_alert_sent"])
        
        return True
    except Exception as exc:
        # Retry up to 3 times with 60-second delays
        raise self.retry(exc=exc, countdown=60, max_retries=3)
```

#### Periodic Task (`apps/compliance/tasks.py`):

```python
@shared_task
def send_compliance_alerts():
    """
    Run DAILY at 6 AM (via Celery Beat).
    Find all "yellow" documents that haven't had alert sent.
    Queue individual task for each.
    """
    today = timezone.localdate()
    window_end = today + timedelta(days=180)
    
    # Find docs expiring in next 180 days, not yet alerted
    yellow_qs = ComplianceDocument.objects.filter(
        yellow_alert_sent__isnull=True,
        expiry_date__gte=today,
        expiry_date__lte=window_end,
    )
    
    for doc in yellow_qs:
        send_yellow_alert_email_task.delay(doc.id)  # Queue task
    
    return yellow_qs.count()  # Return count for logging
```

#### How it works:

```
[6:00 AM] Celery Beat triggers send_compliance_alerts()
  ├─ Query DB: Find docs in "yellow" state not yet alerted
  ├─ For each doc:
  │   └─ send_yellow_alert_email_task.delay(doc.id)  ← Queue message to Redis
  └─ Return count

[Celery Worker picks up task from Redis queue]
  ├─ send_yellow_alert_email_task(doc_id=42)
  ├─ Render email template
  ├─ Send via SMTP
  ├─ Mark yellow_alert_sent = now()
  └─ Return True

[If SMTP fails]
  └─ Task retries after 60 seconds (up to 3 times)
```

**Why async?**
- **Non-blocking:** Email sending (slow, network-dependent) doesn't block user requests.
- **Retry logic:** If mail server is down at 6 AM, task retries and eventually succeeds.
- **Distributed:** Workers can run on separate servers (scales to millions of emails).

---

## SECURITY & PERFORMANCE

### 1. Security Features (Automatic)

#### CSRF Protection (Django Built-In):

**How it works:**
```html
<!-- Form must include CSRF token -->
<form method="post">
    {% csrf_token %}  ← Django injects token here
    <input type="text" name="title">
    <button type="submit">Save</button>
</form>
```

**What happens:**
1. **Form render:** Django generates unique token, stores in session.
2. **Form submit:** Browser sends token in POST data.
3. **Middleware check:** Django validates token matches session (reject if mismatch).

**Why it prevents CSRF:**
- Attacker's malicious site can't read your CSRF token (browsers block cross-domain reads).
- Without token, attacker can't craft valid POST.

**In our code:** Every form automatically gets `{% csrf_token %}` via crispy forms.

#### XSS Protection (Template Auto-Escaping):

**By default:**
```html
<!-- User input automatically escaped -->
<h1>{{ user.full_name }}</h1>

<!-- If user.full_name = "<script>alert('hack')</script>" -->
<!-- Renders as: &lt;script&gt;alert('hack')&lt;/script&gt; -->
<!-- Browser renders as TEXT, not executable code -->
```

**Bypass (dangerous):**
```html
<!-- Unsafe: Use only for trusted content -->
<div>{{ user_bio|safe }}</div>
```

**In our code:** All user inputs (titles, descriptions, etc) are auto-escaped.

#### SQL Injection Protection (ORM):

**Vulnerable code (DON'T DO THIS):**
```python
title = request.GET.get("q")
# Attacker: q='; DROP TABLE expenses; --
expenses = Expense.objects.raw(f"SELECT * FROM expenses WHERE title = '{title}'")
```

**Safe code (WHAT WE DO):**
```python
q = request.GET.get("q", "")
expenses = Expense.objects.filter(title__icontains=q)
# ORM parameterizes query: SELECT * FROM expenses WHERE title ILIKE %q%
# Attacker input treated as literal string, not SQL code
```

**In our code:** All queries use Django ORM (no raw SQL). Example:
```python
def donor_list(request):
    q = request.GET.get("q", "").strip()
    qs = Donor.objects.filter(name__icontains=q)  ← Safe
```

#### Authentication Middleware:

```python
MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    ...
]
```

- Validates session cookies.
- Sets `request.user` to authenticated User (or AnonymousUser).
- Enables `@login_required` decorator.

#### Permission Decorators:

```python
@login_required                  # Redirects to /accounts/login/ if not authenticated
@role_required("admin")          # Redirects if user.role != "admin"
def admin_view(request):
    ...
```

If attacker tries to access `/admin/users/` without permission:
1. `@role_required` checks → Fails
2. Shows error message → "You do not have permission..."
3. Redirects → `/accounts/dashboard/`

---

### 2. Performance Issues & Optimizations

#### Issue #1: N+1 Query Problem

**Example (BAD):**
```python
# Expense list view
expenses = Expense.objects.all()
return render(request, "expense_list.html", {"expenses": expenses})

# Template loops through expenses
{% for expense in expenses %}
    <td>{{ expense.created_by.get_full_name }}</td>
    <!-- For EACH expense, Django queries the User table → N+1 queries! -->
{% endfor %}
```

**Result:**
- 1 query to fetch expenses.
- N queries (one per expense) to fetch user names.
- **Total: 1 + N queries** (slow!)

**Fix (GOOD):**
```python
# Use select_related() for ForeignKey (joins table)
expenses = Expense.objects.filter(is_active=True).select_related("created_by")

# template loop now uses cached user data (no queries)
```

**In our code (correctly done):**
```python
# apps/expenses/views.py
def expense_list(request):
    expenses = Expense.objects.filter(is_active=True)\
        .select_related("created_by")\
        .prefetch_related("allocations__grant")
    # select_related: Fetches User in same query (JOIN)
    # prefetch_related: Fetches Allocations + Grants in separate queries, caches in memory
    return render(request, "expenses/expense_list.html", {"expenses": expenses})
```

**Performance gain:** From 100 expenses → 1 + 1 + 1 = 3 queries (instead of 1 + 100 + 100 = 201).

---

#### Issue #2: Computed Properties in Loops

**Example (BAD):**
```python
# grants/grant_list.html
{% for grant in grants %}
    <tr>
        <td>{{ grant.name }}</td>
        <td>₹{{ grant.utilized_amount }}</td>  <!-- Queries every row! -->
        <td>{{ grant.burn_rate }}</td>          <!-- Queries every row! -->
    </tr>
{% endfor %}
```

**Result:**
- Each `grant.utilized_amount` runs: `self.allocations.aggregate(Sum(...))`
- For 50 grants → 50 queries to sum allocations.

**Why it's bad:**
- Allocations are already prefetch_related (cached), but code re-aggregates each time.

**Fix:**
```python
# Pre-calculate in view
grant_stats = []
for grant in grants:
    grant_stats.append({
        "grant": grant,
        "utilized": grant.utilized_amount,  # Computes once, caches
        "remaining": grant.remaining_amount,
        "burn_rate": grant.burn_rate,
    })
return render(request, "grants/grant_list.html", {"grant_stats": grant_stats})

# Template uses cached data (no queries)
{% for stat in grant_stats %}
    <td>₹{{ stat.utilized }}</td>
{% endfor %}
```

**Recommendation for PaperTrail:** Cache grant stats in Redis if grant counts exceed 100+.

---

#### Issue #3: File Upload Performance

**Current code:**
```python
receipt = models.FileField(upload_to="expenses/receipts/")
```

**Performance concern:**
- Large files (PDFs, images) uploaded to disk.
- No compression or resizing.
- For 1000+ expenses, media/ directory could grow to GBs.

**Optimizations:**
```python
# Option 1: Cloud storage (S3, Google Cloud)
from storages.backends.s3boto3 import S3Boto3Storage
receipt = models.FileField(storage=S3Boto3Storage(), upload_to="expenses/receipts/")

# Option 2: Compress PDFs before upload
import PyPDF2
def compress_pdf(file):
    reader = PyPDF2.PdfReader(file)
    writer = PyPDF2.PdfWriter()
    for page in reader.pages:
        page.compress_content_streams()
        writer.add_page(page)
    return writer  # Return compressed

# Option 3: Async file processing
@shared_task
def process_receipt(file_id):
    # Compress, scan for viruses, generate thumbnail
    ...
```

**Recommendation:** For production, move files to S3/GCS (not local disk). Implement async processing.

---

#### Issue #4: Database Indexes

**Current schema:**
```python
class AuditLog(models.Model):
    ...
    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["changed_by", "-timestamp"]),
        ]
```

**Why these matter:**
- **Query 1:** "Show all changes to this Grant" → Indexed by (content_type, object_id).
- **Query 2:** "Show all deletions in descending date order" → Indexed by (action, -timestamp).
- **Query 3:** "Show all changes by this user" → Indexed by (changed_by, -timestamp).

**Missing index (potential bottleneck):**
```python
# If you query by timestamp alone
AuditLog.objects.filter(timestamp__gte=yesterday)  # No index → Full table scan!
```

**Recommendation:** Add:
```python
models.Index(fields=["-timestamp"])  # For date range queries
```

---

### 3. Suggested Production Optimizations

#### Optimization #1: Cache Compliance Status

**Current (1 query per request):**
```python
def dashboard_view(request):
    docs = ComplianceDocument.objects.all()
    compliance_summary = {
        "green": sum(1 for d in docs if d.status == "green"),
        ...
    }
    # Queries run EVERY request
```

**Optimized (cache for 1 hour):**
```python
from django.core.cache import cache

def dashboard_view(request):
    cache_key = "compliance_summary"
    compliance_summary = cache.get(cache_key)
    
    if compliance_summary is None:
        # Compute once, cache for 3600 seconds
        docs = ComplianceDocument.objects.all()
        compliance_summary = {
            "green": sum(1 for d in docs if d.status == "green"),
            ...
        }
        cache.set(cache_key, compliance_summary, 3600)
    
    return render(request, "dashboard.html", {"compliance_summary": compliance_summary})

# Invalidate cache when a certificate is saved
@receiver(post_save, sender=ComplianceDocument)
def invalidate_compliance_cache(sender, instance, **kwargs):
    cache.delete("compliance_summary")
```

**Impact:** From 1 query per request → 1 query per hour.

---

#### Optimization #2: Pagination for Large Lists

**Current (loads ALL expenses):**
```python
expenses = Expense.objects.all()  # Could be 10,000+ records
return render(request, "expense_list.html", {"expenses": expenses})
```

**Optimized (paginate by 50):**
```python
from django.core.paginator import Paginator

def expense_list(request):
    expenses_list = Expense.objects.all()
    paginator = Paginator(expenses_list, 50)  # 50 per page
    page_number = request.GET.get("page", 1)
    expenses = paginator.get_page(page_number)
    
    return render(request, "expense_list.html", {
        "expenses": expenses,
        "paginator": paginator,
    })

# Template
Page: {% include "pagination.html" %}
{% for expense in expenses %}
    ...
{% endfor %}
```

**Impact:** Memory usage from O(N) → O(1). Load time from 3s → 200ms.

---

#### Optimization #3: Use Database Indexes for Soft Deletes

**Current (no index):**
```python
expenses = Expense.objects.filter(is_active=True)  # Full table scan!
```

**Optimized (add index):**
```python
class Expense(models.Model):
    is_active = BooleanField(default=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
        ]
```

**Create migration:**
```
python manage.py makemigrations
python manage.py migrate
```

**Impact:** Query time from O(N) → O(log N).

---

## FILE-BY-FILE BREAKDOWN

### Project Structure

```
d:\Sakshi\Projects\NGO\PaperTrail/
│
├── papertrail/                          # Main Django config & entry point
│   ├── settings.py                      # ⭐ CRITICAL: Database, apps, security
│   ├── urls.py                          # ⭐ Root URL dispatcher
│   ├── wsgi.py                          # Production app server entry
│   ├── asgi.py                          # WebSocket entry (not used yet)
│   ├── celery.py                        # Celery config for async tasks
│   └── error_views.py                   # 404/500 error handlers
│
├── apps/                                # Modular Django apps
│
│   ├── accounts/                        # User auth + RBAC
│   │   ├── models.py                    # ⭐ Custom User(AbstractUser)
│   │   ├── views.py                     # ⭐ login, dashboard, user_crud
│   │   ├── forms.py                     # LoginForm, UserCreateForm
│   │   ├── urls.py                      # /accounts/login/, /accounts/dashboard/
│   │   ├── decorators.py                # ⭐ @role_required, @finance_required
│   │   └── templates/accounts/          # login.html, dashboard.html
│   │       ├── login.html               # Login form
│   │       ├── dashboard.html           # Compliance + grants + expenses summary
│   │       └── user_list.html           # Admin user management
│   │
│   ├── compliance/                      # Certificate tracking + alerts
│   │   ├── models.py                    # ⭐ ComplianceDocument (FCRA/80G/12A)
│   │   ├── views.py                     # ⭐ upload, edit, list certificates
│   │   ├── forms.py                     # ComplianceDocumentForm with clean()
│   │   ├── utils.py                     # ⭐ is_compliant(), get_compliance_issues()
│   │   ├── tasks.py                     # ⭐ Celery: send_compliance_alerts
│   │   └── templates/compliance/        # document_list.html, document_form.html
│   │
│   ├── expenses/                        # Expense records + grant allocations
│   │   ├── models.py                    # ⭐ Expense + ExpenseAllocation (pivot)
│   │   ├── views.py                     # ⭐ Complex expense_create with formset
│   │   ├── forms.py                     # ⭐ ExpenseForm + AllocationFormSet
│   │   ├── urls.py                      # /expenses/, /expenses/create/
│   │   └── templates/expenses/          # expense_form.html with nested formset
│   │
│   ├── donors/                          # Donor directory
│   │   ├── models.py                    # Donor (individual/org/govt/corporate)
│   │   ├── views.py                     # donor_list (search + filter), donor_crud
│   │   ├── forms.py                     # DonorForm with Bootstrap styling
│   │   └── templates/donors/            # donor_list.html, donor_form.html
│   │
│   ├── grants/                          # Grant management + budget tracking
│   │   ├── models.py                    # ⭐ Grant with computed: utilized_amount, burn_rate
│   │   ├── views.py                     # grant_list, grant_create, grant_detail
│   │   ├── forms.py                     # GrantForm with date validation
│   │   └── templates/grants/            # grant_detail.html, grant_list.html
│   │
│   ├── reports/                         # PDF/Excel generation (not yet built)
│   │   ├── models.py                    # (empty)
│   │   ├── views.py                     # (skeleton)
│   │   └── urls.py                      # (skeleton)
│   │
│   └── audit/                           # Immutable audit trail
│       ├── models.py                    # ⭐ AuditLog (ContentType pattern)
│       ├── signals.py                   # ⭐ Django signals: pre_save, post_save
│       ├── decorators.py                # (unused)
│       ├── views.py                     # log_list view
│       ├── urls.py                      # /audit/logs/
│       └── templates/audit/             # log_list.html
│
├── templates/                           # Shared templates
│   ├── base.html                        # ⭐ Main layout (nav, sidebar, etc)
│   ├── 404.html                         # Page not found
│   ├── 500.html                         # Server error
│   └── pagination.html                  # Reusable pagination
│
├── manage.py                            # Django CLI entry point
├── requirements.txt                     # Python dependencies
├── db.sqlite3                           # SQLite database (dev only)
├── celerybeat-schedule                  # Celery Beat schedule log
└── media/                               # User-uploaded files
    ├── compliance/                      # Certificates
    └── expenses/receipts/               # Receipt PDFs/images
```

### Key Files Explained

#### `papertrail/settings.py` — The Brain

```python
# What it controls:
DEBUG = env.bool("DEBUG", True)  # Show error details (set False in production!)
ALLOWED_HOSTS = ["*"]            # Which domains can connect (restrict in production)
DATABASES = {...}                # DB connection string
INSTALLED_APPS = [...] ← which apps load  
MIDDLEWARE = [...] ← request/response hooks
SECRET_KEY = "..."               # Security token (generate new in production!)
```

**Why it's critical:** One wrong setting causes security breach (DEBUG=True exposes source code, ALLOWED_HOSTS too loose allows spoofing).

---

#### `papertrail/urls.py` — The Router

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("compliance/", include("apps.compliance.urls", namespace="compliance")),
    ...
    path("", RedirectView.as_view(url="/accounts/dashboard/")),
]
```

**How it works:**
1. User visits `/compliance/documents/`
2. Django matches `"compliance/"` → includes `apps.compliance.urls`
3. Within that file, it looks for `""` (empty) or `"documents/"` pattern
4. Executes corresponding view

**Namespaces:** `namespace="compliance"` lets templates use `{% url 'compliance:document_list' %}` instead of hardcoding paths.

---

#### `apps/accounts/decorators.py` — Permission Layer

```python
def role_required(*roles):
    """Check if user.role is in allowed roles"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, "No permission")
                return redirect("accounts:dashboard")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
```

**Why @wraps?** Preserves function metadata (name, docstring) for debugging.

---

#### `apps/audit/signals.py` — The Audit Logger

```python
@receiver(post_save, sender=Expense)
def log_expense_change(sender, instance, created, **kwargs):
    """Django calls this AFTER Expense.save()"""
    user = get_current_user()  # From middleware
    if created:
        AuditLog.log_action(ACTION_CREATED, instance, user)
    else:
        old_instance = get_old_instance(Expense, instance.pk)
        changes = get_field_changes(instance, old_instance)
        if changes:
            AuditLog.log_action(ACTION_UPDATED, instance, user, changes)
```

**When it runs:**
```python
expense.save()
  ├─ pre_save signal fires
  │   └─ capture_expense_old_state() stores old data
  │
  ├─ (actual save to DB)
  │
  └─ post_save signal fires
      └─ log_expense_change() compares old vs new, creates AuditLog
```

---

#### `apps/compliance/tasks.py` — Async Workers

```python
@shared_task(bind=True)
def send_yellow_alert_email_task(self, doc_id):
    """Run in background Celery worker"""
    try:
        # ... send email ...
        return True
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60, max_retries=3)
```

**Production flow:**
1. **6 AM:** Celery Beat fires `send_compliance_alerts()`
2. **Task queues:** For each yellow doc → `send_yellow_alert_email_task.delay(id)`
3. **Redis:** Tasks sit in queue waiting for worker
4. **Worker picks up:** Sends email, marks doc as alerted
5. **Retry:** If SMTP fails, retries 3 times

---

#### `templates/base.html` — The Canvas

```html
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}PaperTrail{% endblock %}</title>
</head>
<body>
    <nav class="sidebar">
        <!-- Navigation items -->
        {% if user.is_admin_role %}
            <a href="...">Users</a>
        {% endif %}
    </nav>
    
    <main>
        {% include "messages.html" %}  <!-- Flash messages (success/error) -->
        {% block content %}{% endblock %}
    </main>
    
    <script src="bootstrap.js"></script>
</body>
</html>
```

**How child templates extend it:**
```html
<!-- expenses/expense_form.html -->
{% extends "base.html" %}

{% block title %}Record Expense{% endblock %}

{% block content %}
    <h1>Record Expense</h1>
    <form method="post">
        ...
    </form>
{% endblock %}
```

**Django renders this as:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Record Expense | PaperTrail</title>  ← From {% block title %}
</head>
<body>
    <nav>...</nav>
    <main>
        <h1>Record Expense</h1>  ← From {% block content %}
        <form>...</form>
    </main>
</body>
</html>
```

---

## COMMON WORKFLOWS

### Workflow 1: User Login

```
1. User visits /accounts/login/
   └─ login_view() GET handler renders login.html

2. User enters credentials, clicks "Login"
   └─ POST to /accounts/login/

3. login_view() POST handler:
   ├─ form = LoginForm(request.POST)
   ├─ form.is_valid()? 
   │  ├─ NO → Re-render with error messages
   │  └─ YES → login(request, user) [sets session cookie]
   └─ redirect to /accounts/dashboard/

4. Each subsequent request:
   ├─ Browser sends session cookie
   ├─ AuthenticationMiddleware validates it
   ├─ Sets request.user = User object
   └─ @login_required passes
```

---

### Workflow 2: Create Expense with Multi-Grant Allocation

```
1. Finance Manager visits /expenses/create/

2. Views renders empty expense form + empty formset (extra=1 blank row)

3. Finance Manager:
   ├─ Enters "Office Rent"
   ├─ Amount: ₹50,000
   ├─ Date: 2024-01-15
   ├─ Uploads receipt.pdf
   └─ Allocates:
       ├─ Grant A: ₹30,000
       └─ Grant B: ₹20,000

4. Form submission:
   ├─ Compliance gate check: All certs exist + not expired? YES
   ├─ Allocation sum check: 30k + 20k == 50k? YES
   ├─ Budget check: Grant A has 45k available, Grant B has 25k available? YES
   └─ All validations pass

5. DB transaction:
   ├─ INSERT INTO Expense (title, amount, date, ...)
   │   └─ post_save signal → AuditLog entry created
   ├─ INSERT INTO ExpenseAllocation (expense_id, grant_id, amount) × 2
   │   └─ post_save signals × 2 → 2 AuditLog entries created
   └─ COMMIT (all or nothing)

6. Redirect to /expenses/<id>/
   └─ Show success message: "Expense recorded successfully"
```

---

### Workflow 3: Compliance Check Blocks Expense

```
1. Admin deletes "80G Certificate" (compliance document)

2. User tries to create expense

3. ExpenseForm.clean() calls is_compliant():
   ├─ Check FCRA exists? YES
   ├─ Check 80G exists? NO ← FAIL
   └─ return False

4. Form raises ValidationError:
   "Compliance gate failed: 80G Certificate is missing."

5. View doesn't proceed, re-renders form with error

6. User sees error and can't create expense until 80G is uploaded
```

---

### Workflow 4: Audit Trail Query

```
1. Auditor visits /audit/logs/

2. audit_list_view() fetches logs:
   ├─ AuditLog.objects.all().order_by("-timestamp")
   └─ Renders as table with columns:
       - Action (Created/Updated/Deleted)
       - What (grant, expense, etc)
       - By whom (user)
       - When (timestamp)
       - Changes (old → new values in JSON)

3. Auditor can filter:
   ├─ By user: /audit/logs/?user=5
   ├─ By action: /audit/logs/?action=updated
   ├─ By model: /audit/logs/?model=expense
   └─ By date range: /audit/logs/?start=2024-01-01&end=2024-12-31

4. Immutable ledger: Auditor CANNOT delete or modify logs
   (only_insert, no UPDATE/DELETE SQL)
```

---

## INTERVIEW TALKING POINTS

### Point 1: "Explain the data model"

**Answer (1 min):**
"The app models 7 entities: User (extended with custom RBAC), Donor (NGO funding sources), Grant (from donor), Expense (spending), ExpenseAllocation (mapping expenses to grants), ComplianceDocument (FCRA/80G/12A certs), and AuditLog (immutable trail).

The key insight is **ExpenseAllocation is a through table**—one expense maps to multiple grants (e.g., office rent split across three funding sources). We validate: allocations sum to expense total, expense date falls within grant period, grant budget isn't exceeded.

All deletes are 'soft' (is_active flag) to preserve audit trail. Foreign keys use PROTECT to prevent orphaned data."

---

### Point 2: "Walk me through expense creation"

**Answer (2 min):**
"When a Finance Manager creates an expense:

1. **Form Layer:** Two forms—main ExpenseForm and AllocationFormSet (inline). Each field validates (receipt required, dates valid).

2. **Compliance Gate:** ExpenseForm.clean() checks if all 3 compliance certs exist and aren't expired. If not, form fails here.

3. **Cross-formset Validation:** Custom `_validate_allocations()` ensures:
   - Sum of allocations = expense total
   - Expense date within grant periods
   - Grant budgets not exceeded

4. **Atomic DB Save:** If all validations pass, we wrap saves in `transaction.atomic()`. Creates Expense record, then each ExpenseAllocation.

5. **Audit Logging:** Each save triggers Django signals (pre_save, post_save) that capture old/new values and create AuditLog entries.

6. **Redirect:** User sees success message and expense detail page.

The whole flow is transactional—if anything fails, no data is written (ACID compliance)."

---

### Point 3: "How does role-based access work?"

**Answer (1.5 min):**
"We have three roles: Admin (full access), Finance (create/edit financials), Auditor (read-only reports).

I implemented a custom `@role_required(*roles)` decorator that wraps view functions. It checks `request.user.role` and either allows or denies. For example:

```python
@login_required
@role_required("admin", "finance")
def grant_create(request):
    ...
```

The middleware stack ensures `request.user` is set before any view runs. If a user lacking permission tries to access `/grants/create/`, the decorator shows an error message and redirects to dashboard.

This is more flexible than Django's built-in @permission_required, which checks object-level perms. We needed role-based gating (simpler for NGO use case)."

---

### Point 4: "How do you track audit logs?"

**Answer (2 min):**
"Audit logging is the heart of this app—NGOs need compliance proof.

I used Django's **signal system**—when models (Expense, Grant, ComplianceDocument) are saved, pre_save and post_save signals fire automatically.

In pre_save, I capture the old instance in thread-local storage. In post_save, I compare old vs new and detect what fields changed. I then call AuditLog.log_action(...) with action, user, timestamp, and a JSON dict of changes.

The AuditLog model uses **ContentType framework**—a generic foreign key pointing to any model. This lets one table track all changes (no separate audit tables).

Why immutable? I prevent all INSERTs into AuditLog (no UPDATE/DELETE). If you try to tamper, you can't. The middleware captures current user, so we always know WHO changed WHAT and WHEN.

Example log entry:
```json
{
  "action": "updated",
  "object_repr": "Office Rent – ₹50000",
  "changed_by": "alice",
  "timestamp": "2024-01-15T10:30:00",
  "changes": {
    "total_amount": {"old": "45000", "new": "50000"}
  }
}
```

This creates a complete audit trail for NGO compliance reports."

---

### Point 5: "What security measures are in place?"

**Answer (1.5 min):**
"Django provides several automatic protections:

1. **CSRF (Cross-Site Request Forgery):** Every form includes {% csrf_token %}, and CsrfViewMiddleware validates it. Attacker's site can't forge POST requests.

2. **XSS (Cross-Site Scripting):** All template variables auto-escape by default. If user enters `<script>`, it renders as text, not code.

3. **SQL Injection:** We use Django ORM exclusively (no raw SQL). Queries are parameterized, so user input is treated as literal text.

4. **Authentication:** Custom User model with password validators (min length, complexity, etc). Sessions validated via middleware.

5. **Authorization:** Role-based decorators (@role_required) and on_delete=PROTECT constraints prevent unauthorized data access/deletion.

6. **Password Storage:** Django uses PBKDF2 hashing + salt by default. Even if DB is breached, passwords are unrecoverable.

Areas for improvement in production:
- Enable DEBUG=False (currently uses default True)
- Force HTTPS + HSTS headers
- Use environment variables for SECRET_KEY (not hardcoded)
- Implement rate limiting (prevent brute-force login attacks)
- Add 2FA for admin accounts"

---

### Point 6: "What if you had 1 million expenses?"

**Answer (2 min):**
"Performance issues:

1. **N+1 Queries:** Currently, listing expenses + showing creator names runs 1 + N queries. We fix with `.select_related('created_by')` (preloads users in JOIN). Keeps it 1-2 queries regardless of expense count.

2. **Computed Properties:** `grant.burn_rate` recalculates aggregation every time. If looped 1M times, that's 1M SUM queries. Fix: compute once in view, cache result in template context.

3. **List Rendering:** Fetching all 1M expenses into memory is infeasible. Solution: paginate (50 per page). Load 50, render, then fetch next 50 on demand.

4. **Compliance Gate:** is_compliant() queries all 3 cert docs every request. Fix: cache result for 1 hour in Redis.

5. **File Storage:** 1M receipts on local disk = disk space issues. Solution: move to S3/GCS.

6. **DB Indexes:** Queries by (is_active, created_at) need index. Without it, Postgres does full table scan.

I'd add:
- Redis caching layer
- Async file processing (compress receipts in Celery)
- PostgreSQL (replaces SQLite)
- Database read replicas for reporting
- Cloudflare CDN for static files"

---

### Point 7: "If Celery goes down, what happens?"

**Answer (1 min):**
"Celery is purely async (non-critical). If Redis broker is down:

1. Compliance alert emails don't send (deferred, not real-time).
2. Tasks stay queued (when Redis/worker restart, they process).
3. HTTP requests are unblocked (operations don't wait for email).

If you NEED emails synchronously, store task results in Django DB instead of Redis. Tasks still run async, but persist in DB.

For NGO compliance, emails can be delayed 24 hrs—not critical path. Expenses still create (email is nice-to-have)."

---

Congratulations! You now understand the full architecture, data flow, security model, and performance trade-offs. You can explain this to any technical interviewer. 🚀

