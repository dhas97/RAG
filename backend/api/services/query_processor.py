"""
query_processor.py — Pre-retrieval query transformation strategies.

WHY TRANSFORM THE QUERY BEFORE RETRIEVAL?
  A user's raw question is often ambiguous or phrased differently from how
  the relevant answer appears in a document.  Three complementary transforms
  address this:

  1. QUERY REWRITING
     Removes pronouns, resolves abbreviations, and makes the query
     self-contained so the retriever doesn't depend on conversation history.

  2. MULTI-QUERY GENERATION
     Generates 2-3 semantically distinct rephrasings.  Different phrasings
     surface different vocabulary used in the source documents — the union of
     the ranked lists is fused with RRF (see retrieval.py).

  3. HyDE (Hypothetical Document Embeddings — Gao et al. 2022)
     The LLM writes a short hypothetical passage that *would* answer the
     question.  This hypothetical passage lives in the same semantic space as
     real document chunks, so embedding it often outperforms embedding the
     raw question.
"""

import google.generativeai as genai
from django.conf import settings

from .embeddings import get_query_embedding


def _flash(temperature: float = 0.3):
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config=genai.GenerationConfig(
            temperature=temperature, max_output_tokens=512
        ),
    )


def rewrite_query(question: str) -> str:
    """Return a cleaner, retrieval-optimised version of the question."""
    prompt = (
        "Rewrite the following question to be specific, self-contained, and "
        "optimised for document retrieval. Return only the rewritten question.\n\n"
        f"Original: {question}"
    )
    try:
        return _flash().generate_content(prompt).text.strip()
    except Exception:
        return question


def generate_hypothetical_document(question: str) -> str:
    """
    HyDE: produce a short passage that *would* answer the question.

    The passage is embedded (not the question itself) for vector retrieval,
    which consistently improves recall for factual queries.
    """
    prompt = (
        "Write a concise 2-4 sentence factual passage that directly answers "
        "the question below. Write as a document excerpt, not as a reply.\n\n"
        f"Question: {question}"
    )
    try:
        return _flash(temperature=0.2).generate_content(prompt).text.strip()
    except Exception:
        return question


def generate_multi_queries(question: str, n: int = 2) -> list:
    """Return n alternative phrasings of the question."""
    prompt = (
        f"Generate {n} distinct rephrasings of the question below. "
        "Each rephrasing should approach the topic from a different angle. "
        f"Return exactly {n} questions, one per line, no numbering.\n\n"
        f"Original: {question}"
    )
    try:
        lines = _flash().generate_content(prompt).text.strip().split("\n")
        return [q.strip() for q in lines if q.strip()][:n]
    except Exception:
        return []


def build_retrieval_embeddings(
    question: str,
    use_hyde: bool = True,
    use_multi_query: bool = True,
) -> list:
    """
    Return a list of query embeddings for hybrid retrieval.

    Always includes the (rewritten) original question.
    Adds HyDE and multi-query variants when the flags are set.
    Failures in individual transforms are silently skipped so the pipeline
    degrades gracefully.
    """
    queries = [rewrite_query(question)]

    if use_multi_query:
        queries.extend(generate_multi_queries(question, n=2))

    if use_hyde:
        try:
            queries.append(generate_hypothetical_document(question))
        except Exception:
            pass

    embeddings = []
    for q in queries:
        try:
            embeddings.append(get_query_embedding(q))
        except Exception:
            pass

    return embeddings
