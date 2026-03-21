"""Celery app for PaperTrail project."""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "papertrail.settings")

app = Celery("papertrail")

# Using a string here means the worker will not have to
# pickle the object when using Windows or multiple processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Celery debug task: {self.request!r}")
