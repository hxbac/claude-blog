"""Phase C: key rotation within one premium-stock rung of generate_hero.py.

Unsplash, Pexels, and Pixabay are a ladder of different services, not slots
of one credential (see generate_hero.py:_try_premium_stock). These tests
pin down rotation *within* one rung: PEXELS_API_KEY then PEXELS_API_KEY_2,
without ever touching the network. `_http_get_json`, `_download_image`, and
`_fit_image_bytes` are monkeypatched stand-ins, never a real socket.

No test in this file may perform a real network call or use a real-looking
credential; every key value here is a sentinel, never a live one.
"""
from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HERO_PATH = ROOT / "scripts" / "generate_hero.py"


@pytest.fixture
def hero_module(monkeypatch):
    """A fresh import per test: rotation cooldown state must not leak."""
    monkeypatch.setenv("CLAUDE_ENV_FILE", "")
    monkeypatch.delenv("AI_CONTENT_ENV_FILE", raising=False)
    spec = importlib.util.spec_from_file_location("generate_hero_rotation", HERO_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_hero_rotation"] = mod
    spec.loader.exec_module(mod)
    return mod


def _http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "status", None, None)


@pytest.fixture(autouse=True)
def _clean_premium_stock_vars(monkeypatch):
    prefixes = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "UNSPLASH_ACCESS_KEY")
    import os
    for name in list(os.environ):
        if name.startswith(prefixes):
            monkeypatch.delenv(name, raising=False)


def _stub_image_pipeline(monkeypatch, hero_module, tmp_path):
    monkeypatch.setattr(hero_module, "_download_image", lambda url: b"fake-bytes")
    monkeypatch.setattr(hero_module, "_fit_image_bytes", lambda data, w, h: data)
    return tmp_path


class TestPexelsRotation:
    def test_first_slot_401_uses_second_slot(self, hero_module, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("PEXELS_API_KEY", "sentinel-not-a-real-key-1")
        monkeypatch.setenv("PEXELS_API_KEY_2", "sentinel-not-a-real-key-2")
        _stub_image_pipeline(monkeypatch, hero_module, tmp_path)
        seen_keys = []

        def fake_get_json(url, headers=None, rotatable_status=()):
            key = (headers or {}).get("Authorization")
            seen_keys.append(key)
            if key == "sentinel-not-a-real-key-1":
                raise _http_error(401)
            return {"photos": [{"src": {"large2x": "https://images.example/a.jpg"}, "photographer": "Jane"}]}

        monkeypatch.setattr(hero_module, "_http_get_json", fake_get_json)

        result = hero_module._try_pexels("coffee", tmp_path, 1200, 630)

        assert result is not None
        assert result["source"] == "pexels"
        assert seen_keys == ["sentinel-not-a-real-key-1", "sentinel-not-a-real-key-2"]
        err = capsys.readouterr().err
        assert "slot 1 rejected" in err
        assert "sentinel-not-a-real-key" not in err

    def test_single_slot_429_exhausts_rung_and_returns_none(self, hero_module, monkeypatch, tmp_path):
        monkeypatch.setenv("PEXELS_API_KEY", "sentinel-not-a-real-key")
        _stub_image_pipeline(monkeypatch, hero_module, tmp_path)

        def fake_get_json(url, headers=None, rotatable_status=()):
            raise _http_error(429)

        monkeypatch.setattr(hero_module, "_http_get_json", fake_get_json)

        result = hero_module._try_pexels("coffee", tmp_path, 1200, 630)

        assert result is None

    def test_no_key_configured_returns_none_without_rotation_noise(self, hero_module, capsys):
        result = hero_module._try_pexels("coffee", Path("/tmp"), 1200, 630)
        assert result is None
        err = capsys.readouterr().err
        assert "keyring" not in err

    def test_non_credential_failure_is_not_blamed_on_the_key(self, hero_module, monkeypatch, tmp_path, capsys):
        """A missing Pillow (or any non-auth failure) inside the pipeline must
        return None quietly, not be misreported as a credential rejection."""
        monkeypatch.setenv("PEXELS_API_KEY", "sentinel-not-a-real-key")
        monkeypatch.setattr(hero_module, "_download_image", lambda url: b"fake-bytes")

        def raise_pillow_missing(data, w, h):
            raise RuntimeError("Pillow is required to enforce --width/--height")

        monkeypatch.setattr(hero_module, "_fit_image_bytes", raise_pillow_missing)

        def fake_get_json(url, headers=None, rotatable_status=()):
            return {"photos": [{"src": {"large2x": "https://images.example/a.jpg"}, "photographer": "Jane"}]}

        monkeypatch.setattr(hero_module, "_http_get_json", fake_get_json)

        result = hero_module._try_pexels("coffee", tmp_path, 1200, 630)

        assert result is None
        err = capsys.readouterr().err
        assert "[image] Pillow is required" in err
        assert "keyring" not in err
        assert "PEXELS_API_KEY" not in err


class TestPixabayRotation:
    def test_first_slot_403_uses_second_slot(self, hero_module, monkeypatch, tmp_path):
        monkeypatch.setenv("PIXABAY_API_KEY", "sentinel-not-a-real-key-1")
        monkeypatch.setenv("PIXABAY_API_KEY_2", "sentinel-not-a-real-key-2")
        _stub_image_pipeline(monkeypatch, hero_module, tmp_path)
        seen_urls = []

        def fake_get_json(url, headers=None, rotatable_status=()):
            seen_urls.append(url)
            if "sentinel-not-a-real-key-1" in url:
                raise _http_error(403)
            return {"hits": [{"largeImageURL": "https://images.example/b.jpg", "user": "Bob"}]}

        monkeypatch.setattr(hero_module, "_http_get_json", fake_get_json)

        result = hero_module._try_pixabay("coffee", tmp_path, 1200, 630)

        assert result is not None
        assert result["source"] == "pixabay"
        assert len(seen_urls) == 2


class TestSingleKeyStillWorks:
    """Regression guard: an existing single-key setup behaves exactly as it
    did before rotation was wired in."""

    def test_single_pexels_key_success_unchanged(self, hero_module, monkeypatch, tmp_path):
        monkeypatch.setenv("PEXELS_API_KEY", "sentinel-not-a-real-key")
        _stub_image_pipeline(monkeypatch, hero_module, tmp_path)

        def fake_get_json(url, headers=None, rotatable_status=()):
            assert headers == {"Authorization": "sentinel-not-a-real-key"}
            return {"photos": [{"src": {"large2x": "https://images.example/a.jpg"}, "photographer": "Jane"}]}

        monkeypatch.setattr(hero_module, "_http_get_json", fake_get_json)

        result = hero_module._try_pexels("coffee", tmp_path, 1200, 630)
        assert result == {"source": "pexels", "path": str(tmp_path / "hero.jpg")}

    def test_premium_stock_ladder_order_is_unsplash_then_pexels_then_pixabay(
        self, hero_module, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("PEXELS_API_KEY", "sentinel-not-a-real-key")
        called = []
        monkeypatch.setattr(hero_module, "_try_unsplash", lambda *a, **k: called.append("unsplash") or None)
        monkeypatch.setattr(
            hero_module,
            "_try_pexels",
            lambda *a, **k: called.append("pexels") or {"source": "pexels", "path": "x"},
        )
        monkeypatch.setattr(hero_module, "_try_pixabay", lambda *a, **k: called.append("pixabay") or None)

        result = hero_module._try_premium_stock("coffee", [], tmp_path, 1200, 630)

        assert result == {"source": "pexels", "path": "x"}
        assert called == ["unsplash", "pexels"]
