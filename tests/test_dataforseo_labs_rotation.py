"""Phase C: key rotation wiring in scripts/dataforseo_labs.py.

Every test mocks requests.post/requests.get directly on the imported
module, exactly like tests/test_dataforseo_labs.py. No test in this file
performs a real network call, and no credential value here is real; every
one is a sentinel.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import dataforseo_labs as dfl
import env_file


def _fake_response(payload):
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


def _raising_response(exc):
    def _raise():
        raise exc

    return SimpleNamespace(json=lambda: {}, raise_for_status=_raise)


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


@pytest.fixture(autouse=True)
def _clean_dataforseo_vars(monkeypatch):
    import os

    prefixes = ("DATAFORSEO_USERNAME", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD")
    for name in list(os.environ):
        if name.startswith(prefixes):
            monkeypatch.delenv(name, raising=False)


def _args(url="https://example.vn/bai-viet", **overrides):
    base = dict(url=url, location=2704, language="vi", limit=100, keyword_filter=None)
    base.update(overrides)
    return SimpleNamespace(**base)


class TestRotationAcrossSlots:
    def test_slot1_task_40200_slot2_succeeds(self, monkeypatch, capsys):
        """Task-level 40100-40399 rotates: proves the task-status path."""
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")
        monkeypatch.setenv("DATAFORSEO_USERNAME_2", "user-2")
        monkeypatch.setenv("DATAFORSEO_PASSWORD_2", "sentinel-pw-2")
        monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)

        rejected_post = _fake_response(
            {"status_code": 20000, "tasks": [{"status_code": 40200, "status_message": "Auth error"}]}
        )
        ok_post = _fake_response(
            {"status_code": 20000, "tasks": [{"id": "task-2", "status_code": 20000, "result": []}]}
        )
        get_response = _fake_response(
            {
                "status_code": 20000,
                "tasks": [{"status_code": 20000, "result": [{"items": [_ranked_keyword_item()]}]}],
            }
        )
        posts = [rejected_post, ok_post]
        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: posts.pop(0))
        monkeypatch.setattr(dfl.requests, "get", lambda *a, **k: get_response)

        dfl.cmd_ranked_keywords(_args())

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "success"
        assert out["total_keywords"] == 1

    def test_slot1_40501_raises_does_not_rotate(self, monkeypatch, capsys):
        """40501 (Invalid Field) is a request bug, not a credential problem:
        must not rotate, even with a second slot configured."""
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")
        monkeypatch.setenv("DATAFORSEO_USERNAME_2", "user-2")
        monkeypatch.setenv("DATAFORSEO_PASSWORD_2", "sentinel-pw-2")

        post_response = _fake_response(
            {"status_code": 20000, "tasks": [{"status_code": 40501, "status_message": "Invalid Field"}]}
        )
        calls = []
        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: calls.append(1) or post_response)

        dfl.cmd_ranked_keywords(_args())

        out = json.loads(capsys.readouterr().out)
        assert "error" in out
        assert out["error"] != "all_slots_failed"
        assert len(calls) == 1  # never tried slot 2

    def test_slot1_40400_raises_does_not_rotate(self, monkeypatch, capsys):
        """40400 (Invalid Path) is a request bug too: never rotate on it."""
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")
        monkeypatch.setenv("DATAFORSEO_USERNAME_2", "user-2")
        monkeypatch.setenv("DATAFORSEO_PASSWORD_2", "sentinel-pw-2")

        post_response = _fake_response(
            {"status_code": 20000, "tasks": [{"status_code": 40400, "status_message": "Invalid Path"}]}
        )
        calls = []
        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: calls.append(1) or post_response)

        dfl.cmd_ranked_keywords(_args())

        out = json.loads(capsys.readouterr().out)
        assert "error" in out
        assert out["error"] != "all_slots_failed"
        assert len(calls) == 1

    def test_slot1_http_500_raises_does_not_rotate(self, monkeypatch):
        """A 500 is a server error, not a rejected credential: rotate() must
        not switch slots, and the caller sees the original exception."""
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")
        monkeypatch.setenv("DATAFORSEO_USERNAME_2", "user-2")
        monkeypatch.setenv("DATAFORSEO_PASSWORD_2", "sentinel-pw-2")

        import requests as real_requests

        error_response = _raising_response(real_requests.exceptions.HTTPError("500 server error"))
        calls = []
        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: calls.append(1) or error_response)

        with pytest.raises(real_requests.exceptions.HTTPError):
            dfl.cmd_ranked_keywords(_args())
        assert len(calls) == 1

    def test_only_one_slot_429_all_slots_failed(self, monkeypatch, capsys):
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")

        import requests as real_requests
        import urllib.request as _u  # noqa: F401  (module attr used below)

        class Resp429:
            status_code = 429

            def json(self):
                return {}

            def raise_for_status(self):
                raise real_requests.exceptions.HTTPError(
                    "429 rejected", response=SimpleNamespace(status_code=429)
                )

        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: Resp429())

        dfl.cmd_ranked_keywords(_args())

        out = json.loads(capsys.readouterr().out)
        assert out["error"] == "all_slots_failed"
        assert "dataforseo" in out["message"]

    def test_no_slot_configured_credentials_missing_message_preserved(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            dfl.cmd_ranked_keywords(_args())
        assert exc_info.value.code == 1
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "error": "missing_credentials",
            "message": "Set DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD.",
        }

    def test_cost_log_records_slot_field_default_and_explicit(self, tmp_path, monkeypatch):
        """dataforseo_costs.py (claude-seo sibling) is exercised directly in
        its own repo's tests; this only pins that env_file.rotate() hands
        back a Slot whose index a caller can log."""
        monkeypatch.setenv("DATAFORSEO_USERNAME", "user-1")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "sentinel-pw-1")
        monkeypatch.setenv("DATAFORSEO_USERNAME_2", "user-2")
        monkeypatch.setenv("DATAFORSEO_PASSWORD_2", "sentinel-pw-2")

        seen_slots = []

        def call(slot):
            seen_slots.append(slot.index)
            if slot.index == 1:
                raise env_file.RotatableError("task 40200: Auth error")
            return "ok"

        result = env_file.rotate("dataforseo", call)
        assert result == "ok"
        assert seen_slots == [1, 2]


class TestSingleKeyRegression:
    """Every assertion here is byte-for-byte what test_dataforseo_labs.py
    already checks; repeated here against the rotation-wired code path to
    make the regression guarantee explicit for this phase."""

    def test_single_key_full_flow_unchanged(self, monkeypatch, capsys):
        monkeypatch.setenv("DATAFORSEO_USERNAME", "u")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "p")
        monkeypatch.setattr(dfl.time, "sleep", lambda *_a: None)

        post_response = _fake_response(
            {"status_code": 20000, "tasks": [{"id": "task-42", "status_code": 20000, "result": []}]}
        )
        get_response = _fake_response(
            {
                "status_code": 20000,
                "tasks": [{"status_code": 20000, "result": [{"items": [_ranked_keyword_item()]}]}],
            }
        )
        monkeypatch.setattr(dfl.requests, "post", lambda *a, **k: post_response)
        monkeypatch.setattr(dfl.requests, "get", lambda *a, **k: get_response)

        dfl.cmd_ranked_keywords(_args(limit=50))

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "success"
        assert out["total_keywords"] == 1
        assert out["keywords"][0]["keyword"] == "dich vu seo"
