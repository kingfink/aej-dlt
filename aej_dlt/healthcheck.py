"""Report scheduled sync outcomes to healthchecks.io.

Modal already emails on a crashed run. healthchecks.io adds the failure modes
that silence cannot signal: a cron that stops firing, and a run that hangs past
its grace period.

Pinging is best effort. A monitoring outage must never become a pipeline
outage, so transport errors are logged and swallowed.
"""

from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Mapping
from urllib.request import Request, urlopen

HEALTHCHECK_URL_ENV = "HEALTHCHECKS_PING_URL"
DEFAULT_TIMEOUT = 5
PING_ATTEMPTS = 3
MAX_BODY_CHARS = 10_000

logger = logging.getLogger(__name__)


def run_with_healthcheck(
    run,
    *,
    ping_url: str | None = None,
    opener=urlopen,
    timeout: int = DEFAULT_TIMEOUT,
):
    """Run ``run`` and report start, success, or failure to healthchecks.io.

    Returns whatever ``run`` returns and re-raises whatever it raises, so the
    Modal failure email still fires. Pings are skipped entirely when no ping
    URL is configured, which keeps local runs and tests off the network.
    """
    url = (ping_url or os.environ.get(HEALTHCHECK_URL_ENV) or "").strip()
    if not url:
        return run()

    _ping(url, "/start", opener=opener, timeout=timeout)
    try:
        result = run()
    except BaseException:
        _ping(url, "/fail", body=traceback.format_exc(), opener=opener, timeout=timeout)
        raise

    _ping(url, "", body=_summarize(result), opener=opener, timeout=timeout)
    return result


def _summarize(result) -> str:
    """Render a load result as ping body text shown in healthchecks.io."""
    if isinstance(result, Mapping):
        return "\n".join(f"{name}: {info}" for name, info in result.items())
    return str(result)


def _ping(url: str, suffix: str, *, opener, timeout: int, body: str | None = None) -> None:
    target = url.rstrip("/") + suffix
    data = body[:MAX_BODY_CHARS].encode("utf-8") if body else None

    for attempt in range(1, PING_ATTEMPTS + 1):
        try:
            with opener(Request(target, data=data, method="POST"), timeout=timeout) as response:
                response.read()
            return
        except Exception:
            if attempt < PING_ATTEMPTS:
                continue
            # The ping URL embeds a write capability token, so log the event only.
            logger.warning(
                "healthchecks.io %s ping failed after %s attempts",
                suffix or "success",
                PING_ATTEMPTS,
                exc_info=True,
            )
