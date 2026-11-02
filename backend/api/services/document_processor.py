"""
document_processor.py — Semantic chunking with parent-child hierarchy.

WHY SENTENCE-AWARE CHUNKING (not fixed character windows)?
  Fixed-size splits break sentences mid-thought, which degrades embedding
  quality — the model must encode an incomplete idea.  Splitting on sentence
  boundaries keeps each chunk semantically coherent.

PARENT-CHILD HIERARCHY:
  Child chunk  — small (~CHILD_SENTENCES sentences, ~75-100 words).
               Used as the *retrieval unit*: a tight scope makes vector
               embeddings precise and BM25 scores meaningful.

  Parent chunk — child + PARENT_PADDING extra sentences on each side.
               Used as *generation context*: wider surrounding text gives the
               LLM enough information to answer without truncated sentences.

SLIDING WINDOW WITH 50% OVERLAP:
  Child windows advance by CHILD_SENTENCES // 2 sentences so every sentence
  appears in at least two chunks. This prevents ideas that straddle a window
  boundary from being split across chunks.

PAGE TRACKING:
  PDFs are extracted page-by-page.  Each sentence carries a page number so
  the response can include accurate citations ("Page 4 of your document").
"""

import io
import nltk
import pdfplumber

nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)

CHILD_SENTENCES = 5   # small window — retrieval precision
PARENT_PADDING = 3    # extra sentences on each side for generation context


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> list:
    """Return a list of {text, page} dicts, one per non-empty PDF page."""
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                pages.append({"text": text, "page": i})
    return pages


def extract_text_from_txt(file_bytes: bytes) -> list:
    """Wrap plain text as a single-page list."""
    text = file_bytes.decode("utf-8", errors="replace")
    return [{"text": text, "page": 1}]


# ---------------------------------------------------------------------------
# Semantic parent-child chunking
# ---------------------------------------------------------------------------

def chunk_pages(pages: list) -> list:
    """
    Build parent-child chunk pairs from a list of {text, page} dicts.

    Returns a list of dicts:
      child_text   — small retrieval unit (CHILD_SENTENCES sentences)
      parent_text  — wider generation context (child + padding on both sides)
      page_number  — page where the child starts
      chunk_index  — 0-based position in the document
    """
    # Flatten all sentences across pages, preserving page numbers.
    all_sentences = []
    for page_data in pages:
        for s in nltk.sent_tokenize(page_data["text"]):
            s = s.strip()
            if s:
                all_sentences.append({"text": s, "page": page_data["page"]})

    if not all_sentences:
        return []

    chunks = []
    step = max(1, CHILD_SENTENCES // 2)  # 50% overlap
    chunk_idx = 0

    for i in range(0, len(all_sentences), step):
        child_sents = all_sentences[i: i + CHILD_SENTENCES]
        if not child_sents:
            break

        child_text = " ".join(s["text"] for s in child_sents)

        parent_start = max(0, i - PARENT_PADDING)
        parent_end = min(len(all_sentences), i + CHILD_SENTENCES + PARENT_PADDING)
        parent_text = " ".join(s["text"] for s in all_sentences[parent_start:parent_end])

        chunks.append({
            "child_text": child_text,
            "parent_text": parent_text,
            "page_number": child_sents[0]["page"],
            "chunk_index": chunk_idx,
        })
        chunk_idx += 1

    return chunks


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def process_uploaded_file(file_bytes: bytes, file_name: str) -> tuple:
    """
    Extract text and produce parent-child chunks.
    Returns (file_type, list_of_chunk_dicts).
    """
    if file_name.lower().endswith(".pdf"):
        pages = extract_text_from_pdf(file_bytes)
        file_type = "pdf"
    elif file_name.lower().endswith(".txt"):
        pages = extract_text_from_txt(file_bytes)
        file_type = "txt"
    else:
        raise ValueError(f"Unsupported file type: {file_name}")

    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("No text could be extracted from the uploaded file.")

    return file_type, chunks


import io
import pdfplumber

