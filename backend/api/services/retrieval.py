"""
retrieval.py — Hybrid retrieval: BM25 keyword search + pgvector ANN search
fused with Reciprocal Rank Fusion (RRF).

WHY HYBRID SEARCH?
  Neither BM25 nor dense vector search is universally better:
  • BM25 excels at exact keyword matches (names, codes, technical terms).
  • Dense search excels at semantic matches where wording differs.
  Combining both with RRF captures what each alone would miss.

WHY QUERY TRANSFORMATION?
  The raw user question is one phrasing of the information need.  We also
  embed HyDE passages and alternative query phrasings so the retriever sees
  the information need from multiple angles, then fuse the ranked lists.

WHY RRF (Reciprocal Rank Fusion)?
  RRF avoids the need to normalise or calibrate scores across different
  retrieval systems.  A document ranked 1st in any list gets a large boost;
  one ranked 100th gets almost none.  It consistently outperforms simple
  score averaging.

  Formula: RRF(d) = Σ 1 / (k + rank_in_list(d)),  k=60 is standard.
"""

from rank_bm25 import BM25Okapi
from pgvector.django import CosineDistance

from .embeddings import get_query_embedding
from .query_processor import build_retrieval_embeddings
from ..models import DocumentChunk

RRF_K = 60  # standard RRF constant — do not change without benchmarking


# ---------------------------------------------------------------------------
# Individual retrieval methods
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list:
    return text.lower().split()


def bm25_search(question: str, top_k: int) -> list:
    """
    BM25 keyword search over all stored child chunks.
    Loads the corpus from the DB on every call; fast enough for thousands
    of chunks and avoids stale in-memory state.
    """
    chunks = list(DocumentChunk.objects.all().select_related("document"))
    if not chunks:
        return []
    bm25 = BM25Okapi([_tokenize(c.text) for c in chunks])
    scores = bm25.get_scores(_tokenize(question))
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]


def vector_search(query_embedding: list, top_k: int) -> list:
    """
    pgvector cosine ANN search — uses the HNSW index created in migration 0002.
    """
    return list(
        DocumentChunk.objects
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")
        .select_related("document")[:top_k]
    )


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(ranked_lists: list, k: int = RRF_K) -> list:
    """
    Merge multiple ranked lists of DocumentChunk objects using RRF.
    Returns a single list sorted by descending RRF score.
    """
    scores = {}
    chunk_map = {}
    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunk_map[chunk.id] = chunk
    return [
        chunk_map[cid]
        for cid in sorted(scores, key=lambda cid: scores[cid], reverse=True)
    ]


# ---------------------------------------------------------------------------
# Full hybrid pipeline
# ---------------------------------------------------------------------------

def hybrid_retrieve(question: str, top_k: int = 5, use_query_transform: bool = True) -> list:
    """
    Full retrieval pipeline:
      1. BM25 keyword search on the original question.
      2. Dense vector search on the original query + HyDE + multi-query
         variants (when use_query_transform=True).
      3. RRF fusion of all ranked lists.

    Returns up to top_k * 3 candidate chunks for the downstream reranker
    to winnow down to the final top_k.
    """
    if not DocumentChunk.objects.exists():
        return []

    fetch_k = min(top_k * 4, 25)
    ranked_lists = []

    # BM25 leg
    bm25_results = bm25_search(question, fetch_k)
    if bm25_results:
        ranked_lists.append(bm25_results)

    # Dense vector leg (possibly multiple query variants)
    if use_query_transform:
        embeddings = build_retrieval_embeddings(question, use_hyde=True, use_multi_query=True)
    else:
        embeddings = [get_query_embedding(question)]

    for emb in embeddings:
        try:
            results = vector_search(emb, fetch_k)
            if results:
                ranked_lists.append(results)
        except Exception:
            pass

    if not ranked_lists:
        return []

    # Return extra candidates so the reranker has enough to work with.
    return reciprocal_rank_fusion(ranked_lists)[: top_k * 3]



