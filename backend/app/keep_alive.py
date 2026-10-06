import asyncio
import logging
import urllib.error
import urllib.request
from typing import Optional

from app.config import settings

logger = logging.getLogger("intellinotes.keep_alive")


def send_ping(url: str, timeout: float = 15.0) -> bool:
    """Send an HTTP GET ping to keep the host active.

    Returns True if the request reached the server (including non-200 responses,
    since any inbound traffic resets the free-tier sleep timer), False on connection failure.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "IntelliNotes-KeepAlive/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", getattr(resp, "code", 200))
            logger.info("Keep-alive self-ping succeeded: %s -> HTTP %d", url, status)
            return True
    except urllib.error.HTTPError as exc:
        # Inbound HTTP reached the server/router, resetting inactivity timer
        logger.info("Keep-alive self-ping reached server: %s -> HTTP %d", url, exc.code)
        return True
    except urllib.error.URLError as exc:
        logger.warning("Keep-alive self-ping connection error: %s (%s)", url, exc.reason)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Keep-alive self-ping unexpected error: %s (%s)", url, exc)
        return False


async def keep_alive_worker(initial_delay_seconds: float = 30.0) -> None:
    """Periodic worker that pings the backend service every N minutes."""
    if not settings.keep_alive_enabled:
        logger.info("Keep-alive worker disabled (KEEP_ALIVE_ENABLED=false).")
        return

    url = settings.resolved_keep_alive_url
    if not url:
        logger.info("Keep-alive worker dormant: no target URL configured.")
        return

    interval_seconds = max(60, settings.keep_alive_interval_minutes * 60)
    logger.info(
        "Keep-alive worker active: targeting %s every %d minutes.",
        url,
        settings.keep_alive_interval_minutes,
    )

    try:
        # Initial ping after short delay to verify server is reachable
        if initial_delay_seconds > 0:
            await asyncio.sleep(initial_delay_seconds)
            target = settings.resolved_keep_alive_url
            if target:
                await asyncio.to_thread(send_ping, target)

        while True:
            await asyncio.sleep(interval_seconds)
            target = settings.resolved_keep_alive_url
            if target:
                await asyncio.to_thread(send_ping, target)
    except asyncio.CancelledError:
        logger.info("Keep-alive worker stopped.")
        raise


def start_keep_alive(initial_delay_seconds: float = 30.0) -> Optional[asyncio.Task]:
    """Start the keep-alive background task if enabled and target URL is known."""
    if not settings.keep_alive_enabled:
        return None
    if not settings.resolved_keep_alive_url:
        return None
    return asyncio.create_task(keep_alive_worker(initial_delay_seconds=initial_delay_seconds))


async def stop_keep_alive(task: Optional[asyncio.Task]) -> None:
    """Gracefully cancel and await the keep-alive task on shutdown."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
