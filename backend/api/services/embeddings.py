"""
embeddings.py — Generates text embeddings via the Gemini embedding model.

TASK-TYPE DIFFERENTIATION:
  The Gemini embedding model is trained with separate task types that shift
  the vector space for the specific use-case:

  RETRIEVAL_DOCUMENT  — used when embedding chunks at index time.
                         Optimised for storing passages that will be compared
                         against user queries.

  RETRIEVAL_QUERY     — used when embedding the user's question (and HyDE
                         hypothetical documents) at query time.
                         Optimised for matching against stored passages.

  Using the correct task type consistently improves retrieval recall compared
  to embedding everything with the same task type.

OUTPUT DIMENSIONALITY:
  EMBEDDING_DIM is set explicitly so the pgvector column size and the
  model output are always in sync.  Change it in one place here and the
  migration / model definition will follow.
"""

import google.generativeai as genai
from django.conf import settings

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 768  # must match VectorField(dimensions=...) in models.py


def _embed(text: str, task_type: str) -> list:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIM,
    )
    return result["embedding"]


def get_document_embedding(text: str) -> list:
    """Embed a chunk at index time (RETRIEVAL_DOCUMENT task type)."""
    return _embed(text, task_type="RETRIEVAL_DOCUMENT")


def get_query_embedding(text: str) -> list:
    """Embed a user query or HyDE passage at query time (RETRIEVAL_QUERY)."""
    return _embed(text, task_type="RETRIEVAL_QUERY")


def get_embedding(text: str) -> list:
    """Backward-compatible alias — defaults to document embedding."""
    return get_document_embedding(text)

