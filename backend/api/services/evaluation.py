"""
evaluation.py — RAG quality metrics (LLM-as-judge).

WHY EVALUATE AT ALL?
  RAG systems can fail silently: the answer sounds plausible but contradicts
  or ignores the retrieved context (hallucination), or the retrieved context
  is irrelevant to the question (bad retrieval).  These three metrics catch
  different failure modes:

  FAITHFULNESS
    Fraction of factual claims in the answer that are grounded in the
    retrieved context.  Low faithfulness = the model is hallucinating.

  ANSWER RELEVANCY
    Does the answer actually address the question asked?
    Low relevancy = the model went off-topic.

  CONTEXT RELEVANCY
    How relevant is the retrieved context to the question?
    Low context relevancy = the retrieval pipeline surfaced the wrong chunks.

WHY LLM-AS-JUDGE?
  Reference-free evaluation (no gold answers required) is the only practical
  option when documents and questions are user-supplied.  LLM scoring
  correlates well with human judgements for factual Q&A tasks.

USAGE:
  Call run_rag_evaluation() after generation to get all three scores.
  Pass evaluate=true in the /api/chat/ request body to include them in
  the API response (adds one extra LLM call per metric).
"""

import google.generativeai as genai
from django.conf import settings


def _judge(temperature: float = 0.0):
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config=genai.GenerationConfig(
            temperature=temperature, max_output_tokens=128
        ),
    )


def _safe_float(text: str) -> float:
    """Extract the first float from a string; return -1.0 on failure."""
    import re
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    return float(match.group()) if match else -1.0


def evaluate_faithfulness(answer: str, chunks: list) -> float:
    """
    Score (0.0–1.0): fraction of answer claims supported by the context.
    Uses parent_text when available for a richer context window.
    """
    context = "\n---\n".join(
        (c.parent_text if getattr(c, "parent_text", None) else c.text)[:600]
        for c in chunks
    )
    prompt = (
        "Context:\n{context}\n\n"
        "Answer:\n{answer}\n\n"
        "What fraction of factual claims in the Answer are directly supported "
        "by the Context?  Return a single float between 0.0 and 1.0 only."
    ).format(context=context, answer=answer)
    try:
        return _safe_float(_judge().generate_content(prompt).text)
    except Exception:
        return -1.0


def evaluate_answer_relevancy(question: str, answer: str) -> float:
    """Score (0.0–1.0): how well the answer addresses the question."""
    prompt = (
        f"Question: {question}\n\n"
        f"Answer: {answer}\n\n"
        "Rate how well the Answer addresses the Question on a scale "
        "from 0.0 to 1.0.  Return a single float only."
    )
    try:
        return _safe_float(_judge().generate_content(prompt).text)
    except Exception:
        return -1.0


def evaluate_context_relevancy(question: str, chunks: list) -> float:
    """Score (0.0–1.0): how relevant the retrieved passages are to the question."""
    passages = "\n---\n".join(c.text[:400] for c in chunks)
    prompt = (
        f"Question: {question}\n\n"
        f"Retrieved passages:\n{passages}\n\n"
        "Rate how relevant the passages are to answering the question on a "
        "scale from 0.0 to 1.0.  Return a single float only."
    )
    try:
        return _safe_float(_judge().generate_content(prompt).text)
    except Exception:
        return -1.0


def run_rag_evaluation(question: str, answer: str, chunks: list) -> dict:
    """Run all three metrics and return them as a dict."""
    return {
        "faithfulness": evaluate_faithfulness(answer, chunks),
        "answer_relevancy": evaluate_answer_relevancy(question, answer),
        "context_relevancy": evaluate_context_relevancy(question, chunks),
    }
