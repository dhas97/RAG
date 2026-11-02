"""
llm.py — Grounded generation with inline citations.

CITATION STRATEGY:
  Context passages are numbered [1], [2], … in the prompt.  The model is
  instructed to add these markers after every factual claim.  The response
  is returned alongside a citations list so the frontend can render
  expandable source cards.

WHY USE parent_text FOR GENERATION?
  Child chunks are small by design (precise retrieval).  Their parent chunks
  include surrounding sentences that give the LLM enough context to write a
  coherent answer without cutting off mid-thought.

TEMPERATURE 0.2:
  Low enough for factual, reproducible answers; slightly above 0 to avoid
  rigid, mechanical phrasing.
"""

import google.generativeai as genai
from django.conf import settings


def _client():
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=1024),
    )


def chat_with_context(question: str, chunks: list) -> dict:
    """
    Generate a grounded answer and return a structured dict.

    Returns:
        answer    — str with inline [1][2] citation markers
        citations — list of {index, document_name, page_number, excerpt}
    """
    model = _client()

    if not chunks:
        response = model.generate_content(
            "You are a helpful assistant. No documents have been uploaded yet. "
            f"Answer from general knowledge.\n\nQuestion: {question}"
        )
        return {"answer": response.text, "citations": []}

    numbered_passages = []
    citations = []
    for i, chunk in enumerate(chunks, start=1):
        # Prefer the wider parent window; fall back to child text.
        passage_text = (chunk.parent_text or chunk.text)
        numbered_passages.append(f"[{i}] {passage_text}")
        citations.append({
            "index": i,
            "document_name": chunk.document.name,
            "page_number": chunk.page_number,
            "excerpt": chunk.text[:200],
        })

    context_block = "\n\n".join(numbered_passages)
    prompt = (
        "You are a precise document Q&A assistant. Answer using ONLY the "
        "numbered passages below. After each factual claim add its citation "
        "number in brackets, e.g. [1]. If the answer is not in the passages, "
        "say so clearly.\n\n"
        f"Passages:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer (with inline citations):"
    )

    response = model.generate_content(prompt)
    return {"answer": response.text, "citations": citations}


import google.generativeai as genai

