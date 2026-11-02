"""
urls.py — Maps URL patterns to the view classes that handle them.

ALL ROUTES ARE PREFIXED WITH /api/ (configured in rag_assistant/urls.py).

ROUTE REFERENCE:
  POST   /api/chat/               — Send a question; receive an AI answer.
  GET    /api/documents/          — Retrieve the list of uploaded documents.
  POST   /api/documents/upload/   — Upload a new file (multipart/form-data).
  DELETE /api/documents/<pk>/     — Delete a document by its integer ID.

WHY ARE UPLOAD AND LIST SEPARATE ROUTES?
  REST convention: the collection resource (GET /documents/) and the
  action that creates a new resource (POST /documents/upload/) are distinct.
  Keeping them separate makes the intent of each request unambiguous and
  allows different authentication or rate-limiting rules per route in future.
"""

from django.urls import path
from .views import ChatView, DocumentListView, DocumentUploadView, DocumentDeleteView, DocumentStatusView

urlpatterns = [
    path('chat/', ChatView.as_view(), name='chat'),
    path('documents/', DocumentListView.as_view(), name='document-list'),
    path('documents/upload/', DocumentUploadView.as_view(), name='document-upload'),
    path('documents/<int:pk>/', DocumentDeleteView.as_view(), name='document-delete'),
    path('documents/<int:pk>/status/', DocumentStatusView.as_view(), name='document-status'),
]
