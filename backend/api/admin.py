"""
admin.py — Registers models in Django's built-in admin panel (/admin/).

WHAT THIS FILE IS:
  Django ships with a full admin UI at /admin/. To make a model visible there
  you must register it here. This file registers Document and DocumentChunk
  so you can browse, search, and delete records without writing SQL.

WHEN IS THIS USEFUL?
  - Inspecting uploaded documents and their chunk counts during development.
  - Manually deleting stuck 'processing' documents if the Celery worker crashed.
  - Checking embedding status without hitting the API.

NOTE: Admin is enabled only when DEBUG=True or when a superuser account exists.
      Run 'python manage.py createsuperuser' to create an admin account.
"""
from django.contrib import admin
from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'file_type', 'status', 'chunks_done', 'chunks_total', 'created_at']
    list_filter = ['status', 'file_type']
    search_fields = ['name']


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ['document', 'chunk_index', 'page_number']
    list_filter = ['document']
    search_fields = ['text']
