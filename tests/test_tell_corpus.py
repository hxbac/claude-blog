"""Phase O: the tell corpus (scripts/tell_corpus.py) wired into analyze_blog."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_blog
import tell_corpus

SLOP = Path(__file__).parent / "fixtures" / "vi_slop_review_sample.md"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(tell_corpus.ENV_VAR, raising=False)


def _post(tmp_path: Path, under_results: bool = True, lang: str = "vi") -> Path:
    d = tmp_path / "ws" / ("blog-results" if under_results else "misc") / "bai-thu"
    d.mkdir(parents=True)
    p = d / "bai-thu.md"
    text = SLOP.read_text(encoding="utf-8")
    p.write_text(text.replace("lang: vi", f"lang: {lang}", 1) if "lang: vi" in text else text,
                 encoding="utf-8")
    return p


def _run(path: Path, *extra: str, env: dict | None = None):
    import os
    e = dict(os.environ)
    e.pop(tell_corpus.ENV_VAR, None)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "analyze_blog.py"), str(path), "--mode", "draft", *extra],
        capture_output=True, text=True, env=e,
    )


def test_records_under_blog_results(tmp_path):
    p = _post(tmp_path)
    assert _run(p).returncode == 0
    f = tmp_path / "ws" / ".metrics" / "tells.jsonl"
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    r = rows[0]
    assert r["slug"] and r["lang"] == "vi" and isinstance(r["score"], int)
    assert isinstance(r["p0"], list) and r["phrases"], "slop sample must match phrases"
    assert all(isinstance(v, int) and v >= 1 for v in r["phrases"].values())
    assert "cluster_score" in r["structure"] and "consistent" in r["register"]
    assert len(r["hash"]) == 16


def test_no_body_stored(tmp_path):
    p = _post(tmp_path)
    _run(p)
    raw = (tmp_path / "ws" / ".metrics" / "tells.jsonl").read_text(encoding="utf-8")
    body_line = [l for l in p.read_text(encoding="utf-8").splitlines() if len(l) > 80][0]
    assert body_line not in raw and len(raw) < 4000


def test_dedupe_same_content_but_new_row_when_edited(tmp_path):
    p = _post(tmp_path)
    _run(p)
    _run(p)
    f = tmp_path / "ws" / ".metrics" / "tells.jsonl"
    assert len(f.read_text(encoding="utf-8").splitlines()) == 1
    p.write_text(p.read_text(encoding="utf-8") + "\nThêm một câu mới.\n", encoding="utf-8")
    _run(p)
    assert len(f.read_text(encoding="utf-8").splitlines()) == 2


def test_not_recorded_outside_blog_results_without_flag(tmp_path):
    p = _post(tmp_path, under_results=False)
    assert _run(p).returncode == 0
    assert not (tmp_path / "ws" / ".metrics").exists()


def test_record_flag_uses_env_override(tmp_path):
    p = _post(tmp_path, under_results=False)
    target = tmp_path / "custom" / "t.jsonl"
    r = _run(p, "--record", env={tell_corpus.ENV_VAR: str(target)})
    assert r.returncode == 0 and len(target.read_text(encoding="utf-8").splitlines()) == 1


def test_english_and_full_mode_not_recorded(tmp_path):
    p = _post(tmp_path)
    res = analyze_blog.analyze_file(str(p), "full")
    assert tell_corpus.maybe_record(p, res) is None
    res = analyze_blog.analyze_file(str(p), "draft")
    res["language"] = "en"
    assert tell_corpus.maybe_record(p, res) is None
    assert not (tmp_path / "ws" / ".metrics").exists()


def test_unwritable_target_is_silent(tmp_path, monkeypatch):
    p = _post(tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv(tell_corpus.ENV_VAR, str(blocker / "sub" / "t.jsonl"))
    res = analyze_blog.analyze_file(str(p), "draft")
    assert tell_corpus.maybe_record(p, res) is None
    r = _run(p, env={tell_corpus.ENV_VAR: str(blocker / "sub" / "t.jsonl")})
    assert r.returncode == 0


def test_corpus_path_rules(tmp_path):
    ws = tmp_path / "w"
    assert tell_corpus.corpus_path(ws / "blog-results" / "a" / "a.md") == ws / ".metrics" / "tells.jsonl"
    assert tell_corpus.corpus_path(ws / "elsewhere" / "a.md") is None
