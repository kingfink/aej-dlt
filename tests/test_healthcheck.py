"""Tests for healthchecks.io pings around the scheduled sync."""

from __future__ import annotations

import pytest

from aej_dlt.healthcheck import HEALTHCHECK_URL_ENV, MAX_BODY_CHARS, run_with_healthcheck

PING_URL = "https://hc-ping.com/11111111-2222-3333-4444-555555555555"


def test_run_without_ping_url_configured_skips_pings(monkeypatch) -> None:
    monkeypatch.delenv(HEALTHCHECK_URL_ENV, raising=False)
    opener = _RecordingOpener()

    result = run_with_healthcheck(lambda: "load info", opener=opener)

    assert result == "load info"
    assert opener.calls == []


def test_blank_ping_url_is_treated_as_unconfigured(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, "   ")
    opener = _RecordingOpener()

    assert run_with_healthcheck(lambda: "load info", opener=opener) == "load info"
    assert opener.calls == []


def test_successful_run_pings_start_then_success_with_summary(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener()

    result = run_with_healthcheck(
        lambda: {"repo_content": "2 jobs loaded", "netlify_forms": "212 submissions"},
        opener=opener,
    )

    assert result == {"repo_content": "2 jobs loaded", "netlify_forms": "212 submissions"}
    assert [call["url"] for call in opener.calls] == [f"{PING_URL}/start", PING_URL]
    assert all(call["method"] == "POST" for call in opener.calls)
    assert opener.calls[0]["body"] is None

    summary = opener.calls[1]["body"]
    assert "repo_content: 2 jobs loaded" in summary
    assert "netlify_forms: 212 submissions" in summary


def test_non_mapping_results_are_summarised_as_text(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener()

    run_with_healthcheck(lambda: "single load info", opener=opener)

    assert opener.calls[1]["body"] == "single load info"


def test_failed_run_pings_fail_with_traceback_and_reraises(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener()

    def boom():
        raise RuntimeError("Cannot add required fields to an existing schema")

    with pytest.raises(RuntimeError, match="Cannot add required fields"):
        run_with_healthcheck(boom, opener=opener)

    assert [call["url"] for call in opener.calls] == [f"{PING_URL}/start", f"{PING_URL}/fail"]

    body = opener.calls[1]["body"]
    assert "RuntimeError" in body
    assert "Cannot add required fields to an existing schema" in body
    assert "Traceback" in body


def test_ping_transport_failure_does_not_break_a_successful_run(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener(error=OSError("healthchecks.io unreachable"))

    assert run_with_healthcheck(lambda: "load info", opener=opener) == "load info"
    assert len(opener.calls) == 2


def test_ping_transport_failure_does_not_mask_the_original_error(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener(error=OSError("healthchecks.io unreachable"))

    def boom():
        raise RuntimeError("pipeline failed")

    with pytest.raises(RuntimeError, match="pipeline failed"):
        run_with_healthcheck(boom, opener=opener)


def test_explicit_ping_url_overrides_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener()

    run_with_healthcheck(lambda: "load info", ping_url="https://hc-ping.com/other", opener=opener)

    assert opener.calls[0]["url"] == "https://hc-ping.com/other/start"


def test_trailing_slash_in_ping_url_does_not_double_up(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, f"{PING_URL}/")
    opener = _RecordingOpener()

    run_with_healthcheck(lambda: "load info", opener=opener)

    assert [call["url"] for call in opener.calls] == [f"{PING_URL}/start", PING_URL]


def test_oversized_body_is_truncated(monkeypatch) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener()

    run_with_healthcheck(lambda: "x" * (MAX_BODY_CHARS * 2), opener=opener)

    assert len(opener.calls[1]["body"]) <= MAX_BODY_CHARS


def test_ping_failures_do_not_log_the_secret_ping_url(monkeypatch, caplog) -> None:
    monkeypatch.setenv(HEALTHCHECK_URL_ENV, PING_URL)
    opener = _RecordingOpener(error=OSError("healthchecks.io unreachable"))

    run_with_healthcheck(lambda: "load info", opener=opener)

    assert "11111111-2222-3333-4444-555555555555" not in caplog.text


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return b"OK"


class _RecordingOpener:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._error = error

    def __call__(self, request, timeout=None):
        self.calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "body": request.data.decode("utf-8") if request.data else None,
                "timeout": timeout,
            }
        )
        if self._error:
            raise self._error
        return _FakeResponse()
