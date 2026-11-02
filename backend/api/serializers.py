"""
serializers.py — Request validation and response serialisation.

TWO SERIALIZERS:

  DocumentSerializer — Converts a Document model instance to JSON.
    Used by: upload response, document list, status endpoint.
    Why chunk_count as a computed field? The chunk count is derived from the
    DocumentChunk table (COUNT(*) WHERE document_id=X). Storing it on Document
    would require keeping it in sync manually. SerializerMethodField computes
    it on demand from the reverse FK relation obj.chunks.count().

  ChatRequestSerializer — Validates POST /api/chat/ body.
    Why a serializer instead of reading request.data directly? Automatic type
    coercion and clear 400 error messages with zero extra if-else logic.
"""

from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id", "name", "file_type", "created_at",
            "status", "chunks_total", "chunks_done", "error_message",
            "chunk_count",
        ]

    def get_chunk_count(self, obj):
        return obj.chunks.count()


class ChatRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    top_k = serializers.IntegerField(default=5, min_value=1, max_value=20)
    # Set evaluate=true to receive faithfulness / relevancy scores (adds latency).
    evaluate = serializers.BooleanField(default=False)
    # Set use_query_transform=false to skip HyDE + multi-query (faster, lower quality).
    use_query_transform = serializers.BooleanField(default=True)
