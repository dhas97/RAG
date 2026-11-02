"""
0002_advanced_rag.py — Migrate to pgvector with parent-child chunk metadata.

WHAT THIS MIGRATION DOES:
  1. Enables the pgvector PostgreSQL extension (CREATE EXTENSION vector).
  2. Drops the old JSON embedding column.
  3. Adds a native vector(768) column for HNSW cosine search.
  4. Adds parent_text — the wider context window sent to the LLM.
  5. Adds page_number — source page for citation metadata.
  6. Creates an HNSW index (O(log n) ANN queries at scale).

NOTE: Re-upload documents after running migrations — old JSON embeddings
cannot be cast to the vector type automatically.
"""

from django.db import migrations, models
from pgvector.django import VectorExtension, VectorField

EMBEDDING_DIM = 768


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        VectorExtension(),  # CREATE EXTENSION IF NOT EXISTS vector
        migrations.RemoveField(model_name="documentchunk", name="embedding"),
        migrations.AddField(
            model_name="documentchunk",
            name="embedding",
            field=VectorField(dimensions=EMBEDDING_DIM, null=True),
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="parent_text",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="page_number",
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS documentchunk_embedding_hnsw "
                "ON api_documentchunk USING hnsw (embedding vector_cosine_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS documentchunk_embedding_hnsw;",
        ),
    ]


