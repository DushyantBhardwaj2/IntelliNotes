import asyncio
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.keep_alive import (
    keep_alive_worker,
    send_ping,
    start_keep_alive,
    stop_keep_alive,
)


def test_keep_alive_url_resolution_explicit():
    settings = Settings(keep_alive_url="https://custom-host.com/ping")
    assert settings.resolved_keep_alive_url == "https://custom-host.com/ping"


def test_keep_alive_url_resolution_render_env():
    with patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://my-render-service.onrender.com"}):
        settings = Settings(keep_alive_url="")
        assert settings.resolved_keep_alive_url == "https://my-render-service.onrender.com/ping"


def test_keep_alive_url_resolution_render_fallback():
    with patch.dict(os.environ, {"RENDER": "true"}, clear=False):
        os.environ.pop("RENDER_EXTERNAL_URL", None)
        settings = Settings(keep_alive_url="")
        assert settings.resolved_keep_alive_url == "https://intellinotes-backend.onrender.com/ping"


def test_keep_alive_url_resolution_local_dormant():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RENDER_EXTERNAL_URL", None)
        os.environ.pop("RENDER", None)
        settings = Settings(keep_alive_url="")
        assert settings.resolved_keep_alive_url == ""


def test_send_ping_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert send_ping("https://intellinotes-backend.onrender.com/ping") is True


def test_send_ping_http_error_still_reached_server():
    http_err = urllib.error.HTTPError(
        url="https://intellinotes-backend.onrender.com/ping",
        code=503,
        msg="Service Unavailable",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        assert send_ping("https://intellinotes-backend.onrender.com/ping") is True


def test_send_ping_connection_failure():
    url_err = urllib.error.URLError(reason="Connection refused")
    with patch("urllib.request.urlopen", side_effect=url_err):
        assert send_ping("https://invalid-host-name-xyz.test/ping") is False


def test_start_keep_alive_disabled():
    with patch("app.keep_alive.settings") as mock_settings:
        mock_settings.keep_alive_enabled = False
        mock_settings.resolved_keep_alive_url = "https://custom.com/ping"
        assert start_keep_alive() is None


def test_start_keep_alive_no_url():
    with patch("app.keep_alive.settings") as mock_settings:
        mock_settings.keep_alive_enabled = True
        mock_settings.resolved_keep_alive_url = ""
        assert start_keep_alive() is None


def test_keep_alive_lifecycle():
    async def _test():
        with patch("app.keep_alive.settings") as mock_settings:
            mock_settings.keep_alive_enabled = True
            mock_settings.resolved_keep_alive_url = "https://test.com/ping"
            mock_settings.keep_alive_interval_minutes = 10

            ping_called = asyncio.Event()

            def fake_ping(url):
                ping_called.set()
                return True

            with patch("app.keep_alive.send_ping", side_effect=fake_ping):
                task = asyncio.create_task(keep_alive_worker(initial_delay_seconds=0.01))
                await asyncio.wait_for(ping_called.wait(), timeout=2.0)
                assert ping_called.is_set()

                await stop_keep_alive(task)
                assert task.done()

    asyncio.run(_test())

