"""
views.py — Django REST API endpoints.

ADVANCED RAG PIPELINE (ChatView):
  Stage 1 — Hybrid retrieval
    hybrid_retrieve() runs BM25 + pgvector ANN search across query
    transformation variants (HyDE, multi-query) and fuses the ranked lists
    with Reciprocal Rank Fusion.  Returns top_k * 3 candidates.

  Stage 2 — LLM reranking
    rerank_chunks() asks Gemini to score each candidate's relevance and keeps
    the top_k highest-scoring chunks.

  Stage 3 — Grounded generation with citations
    chat_with_context() numbers the passages and instructs the model to add
    inline citation markers.  Returns {answer, citations}.

  Stage 4 — Optional evaluation (evaluate=true in request body)
    run_rag_evaluation() computes faithfulness, answer relevancy, and context
    relevancy using Gemini-as-judge.  Adds ~3 extra LLM calls; off by default.

ENDPOINTS:
  POST /api/chat/                 — Ask a question; get answer + citations.
  GET  /api/documents/            — List uploaded documents.
  POST /api/documents/upload/     — Upload a PDF or TXT file.
  DELETE /api/documents/<id>/     — Remove a document and its chunks.
"""

import math
import time

from google.api_core.exceptions import TooManyRequests
from google.rpc.error_details_pb2 import RetryInfo

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser

from .models import Document, DocumentChunk
from .serializers import DocumentSerializer, ChatRequestSerializer
from .services.llm import chat_with_context
from .services.retrieval import hybrid_retrieve
from .services.reranking import rerank_chunks
from .services.document_processor import process_uploaded_file
from .services.embeddings import get_document_embedding
from .services.evaluation import run_rag_evaluation
from .tasks import ingest_document


class ChatView(APIView):
    """
    POST /api/chat/

    Request body (JSON):
      question            str   required
      top_k               int   optional, default 5
      evaluate            bool  optional, default false  (adds latency)
      use_query_transform bool  optional, default true
    """

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data["question"]
        top_k = serializer.validated_data.get("top_k", 5)
        evaluate = serializer.validated_data.get("evaluate", False)
        use_query_transform = serializer.validated_data.get("use_query_transform", True)

        try:
            # Stage 1: hybrid retrieval (BM25 + pgvector + RRF + query transforms)
            candidates = hybrid_retrieve(
                question, top_k=top_k, use_query_transform=use_query_transform
            )

            # Stage 2: LLM reranking — cross-attention relevance scoring
            final_chunks = rerank_chunks(question, candidates, top_k=top_k)

            # Stage 3: grounded generation with inline citations
            result = chat_with_context(question, final_chunks)

            response_data = {
                "answer": result["answer"],
                "citations": result["citations"],
                "sources_used": len(final_chunks),
            }

            # Stage 4: optional evaluation (faithfulness / relevancy metrics)
            if evaluate and final_chunks:
                response_data["evaluation"] = run_rag_evaluation(
                    question, result["answer"], final_chunks
                )

        except TooManyRequests as error:
            retry_after = 60
            for detail in error.details or ():
                if isinstance(detail, RetryInfo):
                    delay = detail.retry_delay
                    retry_after = max(1, math.ceil(delay.seconds + delay.nanos / 1_000_000_000))
                    break
            return Response(
                {
                    "error": (
                        f"Gemini quota exceeded. Try again in {retry_after} seconds. "
                        "If this continues, check your Gemini project quota and billing."
                    ),
                    "retry_after": retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(response_data)


class DocumentListView(APIView):
    """GET /api/documents/  —  list all documents, newest first."""

    def get(self, request):
        documents = Document.objects.all().order_by("-created_at")
        return Response(DocumentSerializer(documents, many=True).data)


class DocumentUploadView(APIView):
    """
    POST /api/documents/upload/

    Validates the file, creates a Document row with status=pending, then
    dispatches the embedding work to a Celery background task and returns
    immediately.  The frontend polls GET /api/documents/<id>/status/ for
    progress.
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        name_lower = file.name.lower()
        if not (name_lower.endswith(".pdf") or name_lower.endswith(".txt")):
            return Response(
                {"error": "Only PDF and TXT files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if file.size > 100 * 1024 * 1024:
            return Response(
                {"error": "File too large. Max size is 100 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = file.read()
        # Pass bytes as hex string — Celery serializes task args as JSON
        file_bytes_hex = file_bytes.hex()

        document = Document.objects.create(
            name=file.name,
            file_type="pdf" if name_lower.endswith(".pdf") else "txt",
            status=Document.STATUS_PENDING,
        )

        ingest_document.delay(document.id, file_bytes_hex, file.name)

        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)


class DocumentStatusView(APIView):
    """GET /api/documents/<pk>/status/  —  returns processing progress."""

    def get(self, request, pk):
        try:
            doc = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "id": doc.id,
            "status": doc.status,
            "chunks_total": doc.chunks_total,
            "chunks_done": doc.chunks_done,
            "error_message": doc.error_message,
        })


class DocumentDeleteView(APIView):
    """DELETE /api/documents/<pk>/  —  cascade-deletes all chunks."""

    def delete(self, request, pk):
        try:
            Document.objects.get(pk=pk).delete()
        except Document.DoesNotExist:
            return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
