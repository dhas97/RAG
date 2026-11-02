"""
models.py — Database schema for the Advanced RAG assistant.

TWO-LEVEL CHUNK HIERARCHY (parent-child retrieval):
  Child chunks are small (sentence-aware, ~5 sentences) — the retrieval unit.
  Parent chunks are the child's wider surrounding context — sent to the LLM.

VECTOR STORAGE:
  Embeddings are stored as native PostgreSQL vector(768) columns via pgvector.
  This enables HNSW approximate nearest-neighbour indexing and SQL-native
  cosine distance ordering — both required for production-scale retrieval.
"""

from django.db import models
from pgvector.django import VectorField

EMBEDDING_DIM = 768  # must match output_dimensionality in embeddings.py


class Document(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)  # 'pdf' or 'txt'
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    chunks_total = models.IntegerField(default=0)
    chunks_done = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')

    def __str__(self):
        return self.name


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    text = models.TextField()         # child chunk — retrieval unit
    parent_text = models.TextField(default="")  # wider window — sent to LLM
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True)
    chunk_index = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["document", "chunk_index"]



