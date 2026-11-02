from unittest.mock import patch

from django.test import SimpleTestCase
from google.api_core.exceptions import ResourceExhausted
from google.protobuf.duration_pb2 import Duration
from google.rpc.error_details_pb2 import RetryInfo
from rest_framework.test import APIRequestFactory

from .views import ChatView


class ChatQuotaTests(SimpleTestCase):
    def request_with_failure(self, error):
        request = APIRequestFactory().post(
            "/api/chat/", {"question": "What is in the document?"}, format="json"
        )
        with patch("api.views.hybrid_retrieve", side_effect=error):
            return ChatView.as_view()(request)

    def test_quota_response_uses_provider_retry_delay(self):
        error = ResourceExhausted(
            "Quota exceeded",
            details=[RetryInfo(retry_delay=Duration(seconds=45, nanos=715587848))],
        )
        response = self.request_with_failure(error)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["retry_after"], 46)
        self.assertEqual(response["Retry-After"], "46")
        self.assertIn("Try again in 46 seconds", response.data["error"])

    def test_quota_response_without_retry_delay(self):
        response = self.request_with_failure(ResourceExhausted("Quota exceeded"))

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["retry_after"], 60)
        self.assertEqual(response["Retry-After"], "60")

    def test_other_errors_remain_server_errors(self):
        response = self.request_with_failure(RuntimeError("Unexpected failure"))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["error"], "Unexpected failure")