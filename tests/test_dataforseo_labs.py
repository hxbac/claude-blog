"""Tests for scripts/dataforseo_labs.py, the DataForSEO Labs wrapper that
skills/blog-cannibalization/SKILL.md documents but that did not exist before
Phase 4 of the Vietnamese language support plan.

Every test that reaches the request/poll code path mocks `requests.post` and
`requests.get` directly on the imported module. No test in this file may
perform a real network call: DataForSEO Labs bills per task, and a test
suite that spends money is a test suite people stop running.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

import dataforseo_labs as dfl

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "dataforseo_labs.py"


def _fake_response(payload):
    """A minimal stand-in for requests.Response: .json() and raise_for_status()."""
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


def _ranked_keyword_item():
    return {
        "keyword_data": {
            "keyword": "dich vu seo",
            "keyword_info": {"search_volume": 1000, "cpc": 0.5, "competition": 0.3},
        },
        "ranked_serp_element": {
            "serp_item": {"rank_absolute": 3, "url": "https://example.vn/bai-viet"}
        },
    }


# ---------------------------------------------------------------------------
# Credential fallback: the whole point of this wrapper
# ---------------------------------------------------------------------------

def test_username_env_var_is_accepted(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "user-a")
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "secret")
    username, password = dfl._get_credentials()
    assert username == "user-a"
    assert password == "secret"


def test_login_env_var_is_accepted_as_fallback(monkeypatch):
    """claude-seo uses DATAFORSEO_USERNAME; this repository's SKILL.md has
    always documented DATAFORSEO_LOGIN. Both must work from one export."""
    monkeypatch.delenv("DATAFORSEO_USERNAME", raising=False)
    monkeypatch.setenv("DATAFORSEO_LOGIN", "user-b")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "secret")
    username, password = dfl._get_credentials()
    assert username == "user-b"
    assert password == "secret"


def test_username_takes_precedence_over_login(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "user-a")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "user-b")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "secret")
    username, _ = dfl._get_credentials()
    assert username == "user-a"


# ---------------------------------------------------------------------------
# Missing credentials: structured exit, not a traceback
# ---------------------------------------------------------------------------

def test_missing_credentials_raises_structured_system_exit(monkeypatch, capsys):
    monkeypatch.delenv("DATAFORSEO_USERNAME", raising=False)
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        dfl._get_credentials()
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out == {
        "error": "missing_credentials",
        "message": "Set DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD.",
    }


def test_missing_credentials_subprocess_exits_clean_no_traceback():
    """End-to-end: run the real script as a subprocess with no credentials
    in the environment at all, and confirm a clean structured exit. This is
    the only subprocess test in the file precisely because it is the only
    path that provably never reaches the network."""
    env = dict(os.environ)
    for key in ("DATAFORSEO_USERNAME", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "ranked-keywords", "https://example.vn"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "error": "missing_credentials",
        "message": "Set DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD.",
    }


# ---------------------------------------------------------------------------
# Credentials are never printed, logged, or returned
# ---------------------------------------------------------------------------

def test_auth_header_and_raw_credentials_never_reach_stdout_or_stderr(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "topsecretuser")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "topsecretpass")
    username, password = dfl._get_credentials()
    headers = dfl._auth_header(username, password)
    captured = capsys.readouterr()
    for stream in (captured.out, captured.err):
        assert "topsecretuser" not in stream
        assert "topsecretpass" not in stream
        assert headers["Authorization"] not in stream


def test_full_ranked_keywords_flow_never_prints_credentials(monkeypatch, capsys):
    """Run the whole ranked-keywords command with mocked HTTP and check the
    entire captured stdout/stderr, not just one function's output, for the
    raw credentials or the encoded Basic auth token."""
    monkeypatch.setenv("DATAFORSEO_USERNAME", "topsecretuser")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "topsecretpass")
    monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)

    post_response = _fake_response(
        {"status_code": 20000, "tasks": [{"id": "task-1", "status_code": 20000, "result": []}]}
    )
    get_response = _fake_response(
        {
            "status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{"items": [_ranked_keyword_item()]}]}],
        }
    )
    monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: post_response)
    monkeypatch.setattr(dfl.requests, "get", lambda *a, **k: get_response)

    args = SimpleNamespace(
        url="https://example.vn/bai-viet",
        location=2704,
        language="vi",
        limit=100,
        keyword_filter=None,
    )
    dfl.cmd_ranked_keywords(args)

    captured = capsys.readouterr()
    token = dfl._auth_header("topsecretuser", "topsecretpass")["Authorization"]
    for stream in (captured.out, captured.err):
        assert "topsecretuser" not in stream
        assert "topsecretpass" not in stream
        assert token not in stream


def test_requests_import_is_guarded_with_structured_error():
    """Static contract check on the source: `requests` must be imported
    behind a try/except that emits the same structured JSON shape as
    claude-seo/scripts/dataforseo_merchant.py, rather than crashing with a
    bare ImportError traceback when the library is absent."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "try:\n    import requests" in source
    assert "except ImportError:" in source
    assert '"requests library required. Install with: pip install requests"' in source


# ---------------------------------------------------------------------------
# Vietnam defaults
# ---------------------------------------------------------------------------

def test_ranked_keywords_defaults_to_vietnam(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    captured = {}

    def fake_post_task(endpoint_key, payload, headers):
        captured["endpoint_key"] = endpoint_key
        captured["payload"] = payload
        return {"error": "api_error", "message": "stop before any network call"}

    monkeypatch.setattr(dfl, "_post_task", fake_post_task)
    monkeypatch.setattr(sys, "argv", ["dataforseo_labs.py", "ranked-keywords", "https://example.vn"])
    dfl.main()

    assert captured["endpoint_key"] == "ranked_keywords"
    payload = captured["payload"][0]
    assert payload["location_code"] == 2704
    assert payload["language_code"] == "vi"


def test_page_intersection_defaults_to_vietnam(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    captured = {}

    def fake_post_task(endpoint_key, payload, headers):
        captured["endpoint_key"] = endpoint_key
        captured["payload"] = payload
        return {"error": "api_error", "message": "stop before any network call"}

    monkeypatch.setattr(dfl, "_post_task", fake_post_task)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dataforseo_labs.py", "page-intersection", "https://example.vn/a", "https://example.vn/b"],
    )
    dfl.main()

    assert captured["endpoint_key"] == "page_intersection"
    payload = captured["payload"][0]
    assert payload["location_code"] == 2704
    assert payload["language_code"] == "vi"
    assert payload["pages"] == {"1": "https://example.vn/a", "2": "https://example.vn/b"}


def test_page_intersection_requires_at_least_two_urls(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    monkeypatch.setattr(sys, "argv", ["dataforseo_labs.py", "page-intersection", "https://example.vn/a"])
    with pytest.raises(SystemExit) as exc_info:
        dfl.main()
    assert exc_info.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# Vietnamese keywords must be NFC-normalized before being sent
# ---------------------------------------------------------------------------

def test_keyword_filter_is_nfc_normalized_before_payload(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")

    nfc_keyword = "Hướng dẫn"
    nfd_keyword = unicodedata.normalize("NFD", nfc_keyword)
    assert nfd_keyword != nfc_keyword  # sanity: NFD really differs byte-for-byte

    captured = {}

    def fake_post_task(endpoint_key, payload, headers):
        captured["payload"] = payload
        return {"error": "api_error", "message": "stop before any network call"}

    monkeypatch.setattr(dfl, "_post_task", fake_post_task)
    args = SimpleNamespace(
        url="https://example.vn/bai-viet",
        location=2704,
        language="vi",
        limit=100,
        keyword_filter=nfd_keyword,
    )
    dfl.cmd_ranked_keywords(args)

    sent_fragment = captured["payload"][0]["filters"][0][2]
    assert unicodedata.is_normalized("NFC", sent_fragment)
    assert nfc_keyword in sent_fragment
    assert nfd_keyword not in sent_fragment


# ---------------------------------------------------------------------------
# Full mocked flow: response normalization
# ---------------------------------------------------------------------------

def test_ranked_keywords_full_flow_normalizes_output(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)

    post_calls = []
    get_calls = []
    post_response = _fake_response(
        {"status_code": 20000, "tasks": [{"id": "task-42", "status_code": 20000, "result": []}]}
    )
    get_response = _fake_response(
        {
            "status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{"items": [_ranked_keyword_item()]}]}],
        }
    )

    def fake_post(*args, **kwargs):
        post_calls.append((args, kwargs))
        return post_response

    def fake_get(*args, **kwargs):
        get_calls.append((args, kwargs))
        return get_response

    monkeypatch.setattr(dfl.requests, "post", fake_post)
    monkeypatch.setattr(dfl.requests, "get", fake_get)

    args = SimpleNamespace(
        url="https://example.vn/bai-viet", location=2704, language="vi", limit=50, keyword_filter=None
    )
    dfl.cmd_ranked_keywords(args)

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "success"
    assert out["total_keywords"] == 1
    keyword = out["keywords"][0]
    assert keyword["keyword"] == "dich vu seo"
    assert keyword["search_volume"] == 1000
    assert keyword["position"] == 3
    assert len(post_calls) == 1
    assert len(get_calls) == 1


def test_page_intersection_full_flow_normalizes_positions(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)

    intersection_item = {
        "keyword_data": {
            "keyword": "may loc nuoc",
            "keyword_info": {"search_volume": 2000, "cpc": 0.8},
        },
        "intersection_result": {
            "1": {"rank_absolute": 2},
            "2": {"rank_absolute": 5},
        },
    }
    post_response = _fake_response(
        {"status_code": 20000, "tasks": [{"id": "task-99", "status_code": 20000, "result": []}]}
    )
    get_response = _fake_response(
        {
            "status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{"items": [intersection_item]}]}],
        }
    )
    monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: post_response)
    monkeypatch.setattr(dfl.requests, "get", lambda *a, **k: get_response)

    args = SimpleNamespace(
        urls=["https://example.vn/a", "https://example.vn/b"],
        location=2704,
        language="vi",
        keyword_filter=None,
    )
    dfl.cmd_page_intersection(args)

    out = json.loads(capsys.readouterr().out)
    assert out["total_overlapping_keywords"] == 1
    positions = out["keywords"][0]["positions"]
    assert positions["https://example.vn/a"] == 2
    assert positions["https://example.vn/b"] == 5


def test_poll_timeout_surfaces_as_structured_error_not_an_exception(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(dfl, "POLL_MAX_ATTEMPTS", 1)

    post_response = _fake_response(
        {"status_code": 20000, "tasks": [{"id": "task-1", "status_code": 20000, "result": []}]}
    )
    # Task never leaves the queue (40601) inside the one allotted attempt.
    stuck_in_queue = _fake_response(
        {"status_code": 20000, "tasks": [{"status_code": 40601, "result": []}]}
    )
    monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: post_response)
    monkeypatch.setattr(dfl.requests, "get", lambda *a, **k: stuck_in_queue)

    args = SimpleNamespace(
        url="https://example.vn/bai-viet", location=2704, language="vi", limit=100, keyword_filter=None
    )
    dfl.cmd_ranked_keywords(args)

    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "poll_timeout"


def test_api_error_response_surfaces_as_structured_error(monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
    error_response = _fake_response({"status_code": 40501, "status_message": "Invalid Field"})
    monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: error_response)

    args = SimpleNamespace(
        url="https://example.vn/bai-viet", location=2704, language="vi", limit=100, keyword_filter=None
    )
    dfl.cmd_ranked_keywords(args)

    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "api_error"
    assert out["message"] == "Invalid Field"
