"""
tasks.py — Celery background tasks for document ingestion.

WHAT THIS FILE IS:
  Contains the `ingest_document` task — the function that does all the slow
  work of embedding a document's chunks. It runs in the Celery worker process,
  completely separate from the Django HTTP process.

WHY A BACKGROUND TASK?
  Embedding a 344-page PDF produces ~2,050 chunks. Each chunk requires one
  Gemini API call. With the free-tier rate limit (100 req/min), this takes
  30–40 minutes. Doing that work inside an HTTP request would timeout the
  browser connection (~60s). Moving it here lets the upload endpoint return
  a 202 Accepted response in ~1 second.

PROGRESS TRACKING:
  The task updates Document.chunks_done every 50 chunks. The frontend polls
  GET /api/documents/<id>/status/ every 2 seconds to show a live progress bar.

STATUS FLOW:
  pending → processing → done
                      ↘ failed  (on any exception)

RATE LIMIT HANDLING:
  Gemini free tier allows ~100 embedding requests/minute. The task sleeps 60s
  after every 80 chunks to stay within the limit.
"""
import time
from celery import shared_task
from .models import Document, DocumentChunk
from .services.document_processor import process_uploaded_file
from .services.embeddings import get_document_embedding


@shared_task(bind=True, max_retries=0)
def ingest_document(self, document_id: int, file_bytes_hex: str, file_name: str):
    """Embed all chunks for a document and save them. Runs in the Celery worker."""
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return

    try:
        document.status = Document.STATUS_PROCESSING
        document.save(update_fields=['status'])

        file_bytes = bytes.fromhex(file_bytes_hex)
        file_type, chunks = process_uploaded_file(file_bytes, file_name)

        document.file_type = file_type
        document.chunks_total = len(chunks)
        document.chunks_done = 0
        document.save(update_fields=['file_type', 'chunks_total', 'chunks_done'])

        chunk_objects = []
        for i, chunk_data in enumerate(chunks):
            embedding = get_document_embedding(chunk_data["child_text"])
            chunk_objects.append(DocumentChunk(
                document=document,
                text=chunk_data["child_text"],
                parent_text=chunk_data["parent_text"],
                embedding=embedding,
                chunk_index=i,
                page_number=chunk_data.get("page_number"),
            ))
            # Flush every 50 chunks so progress updates are visible
            if len(chunk_objects) >= 50:
                DocumentChunk.objects.bulk_create(chunk_objects)
                document.chunks_done = i + 1
                document.save(update_fields=['chunks_done'])
                chunk_objects = []

            # Respect Gemini free-tier rate limit (~100 req/min)
            if (i + 1) % 80 == 0:
                time.sleep(60)

        if chunk_objects:
            DocumentChunk.objects.bulk_create(chunk_objects)

        document.chunks_done = len(chunks)
        document.status = Document.STATUS_DONE
        document.save(update_fields=['chunks_done', 'status'])

    except Exception as exc:
        document.status = Document.STATUS_FAILED
        document.error_message = str(exc)
        document.save(update_fields=['status', 'error_message'])
        raise
