"""Tests for deployment hardening: API-key auth, rate limiting, CORS, errors.

Auth is INERT when API_KEY is unset, so most existing tests run unmodified.
These tests flip the setting per-test and restore it afterwards.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import RateLimiter

client = TestClient(app)


def test_health_is_public_without_auth():
    """/health must stay reachable for platform healthchecks regardless of auth."""
    response = client.get("/health")
    assert response.status_code == 200


def test_documents_list_is_public_without_auth():
    """With auth disabled (local default), GET /documents stays open."""
    response = client.get("/documents")
    assert response.status_code == 200


class TestApiKeyAuth:
    def test_chat_rejected_without_key(self):
        with patch.object(settings, "api_key", "secret-key"):
            response = client.post("/chat/", json={"message": "hi"})
        assert response.status_code == 401
        assert "X-API-Key" in response.json()["detail"]

    def test_chat_rejected_with_wrong_key(self):
        with patch.object(settings, "api_key", "secret-key"):
            response = client.post(
                "/chat/",
                json={"message": "hi"},
                headers={"X-API-Key": "wrong"},
            )
        assert response.status_code == 401

    def test_chat_accepted_with_correct_key(self):
        with (
            patch.object(settings, "api_key", "secret-key"),
            patch("app.main.get_graph") as mock_get_graph,
        ):
            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {"answer": "ok", "trace": []}
            mock_get_graph.return_value = mock_graph
            response = client.post(
                "/chat/",
                json={"message": "hi"},
                headers={"X-API-Key": "secret-key"},
            )
        assert response.status_code == 200

    def test_delete_all_requires_key(self):
        """The destructive clear-all endpoint must never be unauthenticated."""
        with patch.object(settings, "api_key", "secret-key"):
            response = client.delete("/documents/")
        assert response.status_code == 401

    def test_upload_requires_key(self):
        with patch.object(settings, "api_key", "secret-key"):
            response = client.post(
                "/upload-document/",
                files={"file": ("x.pdf", b"data", "application/pdf")},
            )
        assert response.status_code == 401

    def test_read_endpoints_stay_public_when_auth_enabled(self):
        """/health and /docs must remain open even with auth on (platform probes)."""
        with patch.object(settings, "api_key", "secret-key"):
            assert client.get("/health").status_code == 200
            assert client.get("/").status_code == 200


class TestRateLimiter:
    def test_blocks_after_limit(self):
        limiter = RateLimiter(limit=3, window_seconds=60)
        for _ in range(3):
            limiter.check("caller-a")
        try:
            limiter.check("caller-a")
            blocked = False
        except Exception:
            blocked = True
        assert blocked

    def test_callers_are_isolated(self):
        limiter = RateLimiter(limit=1, window_seconds=60)
        limiter.check("caller-a")
        try:
            limiter.check("caller-b")
            blocked = False
        except Exception:
            blocked = True
        assert not blocked

    def test_zero_limit_disables(self):
        limiter = RateLimiter(limit=0)
        for _ in range(100):
            limiter.check("caller-a")  # must never raise

    def test_window_slides(self):
        import time

        limiter = RateLimiter(limit=1, window_seconds=0.05)
        limiter.check("caller-a")
        time.sleep(0.1)
        limiter.check("caller-a")  # old hit expired; allowed again

    def test_chat_endpoint_returns_429_when_exhausted(self):
        from app.main import chat_limiter

        original_limit = chat_limiter.limit
        try:
            chat_limiter._hits.clear()  # isolate from other tests' hits
            chat_limiter.limit = 1
            with patch("app.main.get_graph") as mock_get_graph:
                mock_graph = MagicMock()
                mock_graph.invoke.return_value = {"answer": "ok", "trace": []}
                mock_get_graph.return_value = mock_graph
                first = client.post("/chat/", json={"message": "hi"})
                second = client.post("/chat/", json={"message": "hi again"})
        finally:
            chat_limiter.limit = original_limit
            chat_limiter._hits.clear()
        assert first.status_code == 200
        assert second.status_code == 429
        assert "Retry-After" in second.headers


class TestErrorSanitization:
    def test_agent_failure_returns_generic_detail(self):
        with patch("app.main.get_graph") as mock_get_graph:
            mock_get_graph.side_effect = RuntimeError(
                "C:\\Users\\secret\\path key=AIzaSY leaked"
            )
            response = client.post("/chat/", json={"message": "hi"})
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "AIzaSY" not in detail
        assert "C:\\Users" not in detail
        assert "could not process" in detail
