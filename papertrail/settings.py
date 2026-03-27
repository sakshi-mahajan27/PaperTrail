"""
Django settings for papertrail project.
"""

from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# django-environ: read environment variables from a .env file (for local dev)
env = environ.Env(DEBUG=(bool, True))
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY: load secret key from environment
SECRET_KEY = env("SECRET_KEY", default="django-insecure-rd99bvnffllhbwf5n$bi#3$87asvf6$!8v53i*0@ovnvq0hg0c")

# DEBUG controlled by environment (default True for local development)
DEBUG = env.bool("DEBUG", True)

ALLOWED_HOSTS = ["*"]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "crispy_forms",
    "crispy_bootstrap5",
    # Project apps
    "apps.accounts",
    "apps.audit",
    "apps.compliance",
    "apps.donors",
    "apps.grants",
    "apps.expenses",
    "apps.reports",
    # Celery / async
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Audit logging middleware
    "apps.audit.signals.AuditMiddlewareUser",
]

ROOT_URLCONF = "papertrail.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "papertrail.wsgi.application"


# Database – PostgreSQL (production)
# To switch to PostgreSQL, change ENGINE to django.db.backends.postgresql
# and fill in NAME, USER, PASSWORD, HOST, PORT.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Celery configuration
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Example periodic task schedule (runs daily at 06:00 server time)
from celery.schedules import crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {
    "send-compliance-alerts-daily": {
        "task": "apps.compliance.tasks.send_compliance_alerts",
        "schedule": crontab(hour=6, minute=0),
    },
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Crispy forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Email configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="sakshimahajan0406@gmail.com")
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="sakshimahajan0406@gmail.com")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

# Mail debug logging for SMTP activity
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django.core.mail": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 1800  # 30 minutes