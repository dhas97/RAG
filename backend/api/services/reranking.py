"""
reranking.py — LLM-as-judge cross-attention reranking.

WHY RERANK AFTER RETRIEVAL?
  Vector similarity and BM25 are fast but shallow — they judge a chunk by how
  closely its words or embedding match the query *in isolation*.  A reranker
  considers the *joint* meaning of (query, chunk) together, which catches
  cases where a chunk is topically adjacent to the query but doesn't actually
  answer it.

WHY LLM-AS-JUDGE (vs. a local cross-encoder)?
  A local cross-encoder (e.g. ms-marco-MiniLM) would add a large torch
  dependency to the Docker image.  Using Gemini keeps the dependency footprint
  minimal and leverages the same model already used for generation.  The
  scoring call uses temperature=0 for deterministic scores.

BATCH SCORING STRATEGY:
  All candidates are scored in a single LLM call rather than one call per
  chunk.  This reduces latency and API cost — the model is asked to return a
  JSON array of integer scores (1–10), which is then used to sort the chunks.
"""

import json
import google.generativeai as genai
from django.conf import settings


def rerank_chunks(question: str, chunks: list, top_k: int) -> list:
    """
    Score each chunk for relevance to *question* and return the top_k chunks.

    Scoring is done in one Gemini call.  On any parse failure the function
    falls back to the original order, so retrieval still works.
    """
    if not chunks or len(chunks) <= top_k:
        return chunks[:top_k]

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config=genai.GenerationConfig(temperature=0.0, max_output_tokens=256),
    )

    # Truncate each chunk to 400 chars so the prompt fits in the context window.
    passages = "\n\n".join(
        f"[{i + 1}] {chunk.text[:400]}" for i, chunk in enumerate(chunks)
    )
    prompt = (
        f"Question: {question}\n\n"
        "Rate each passage on how relevant it is to answering the question.\n"
        f"Return a JSON array of {len(chunks)} integers (1=not relevant, "
        "10=highly relevant), one score per passage, in order.\n"
        "Example for 3 passages: [8, 2, 6]\n\n"
        f"Passages:\n{passages}\n\n"
        "JSON scores:"
    )

    try:
        text = model.generate_content(prompt).text.strip()
        start, end = text.find("["), text.rfind("]") + 1
        scores = json.loads(text[start:end])
        ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in ranked[:top_k]]
    except Exception:
        return chunks[:top_k]
