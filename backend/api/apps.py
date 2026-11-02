"""
apps.py — Django app configuration for the 'api' application.

WHAT THIS FILE IS:
  Every Django app needs an AppConfig class. Django uses it to:
    - Register the app in INSTALLED_APPS under the name 'api'.
    - Set the default primary key type for all models in this app.
    - Provide a hook (ready()) for app-startup signals if needed later.

WHY BigAutoField?
  BigAutoField uses a 64-bit integer for primary keys instead of the default
  32-bit IntegerField. 32-bit PKs overflow at ~2 billion rows — safe today,
  but BigAutoField is Django's own recommended default since Django 3.2.
"""
from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
