"""Gate 4 binds the review to the draft it saw; Gate 5 and publish treat
reserved hosts as placeholders instead of allowlisting them."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "scripts" / "blog_preflight.py"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def pf(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_BLOG_REVIEW_STATE_DIR", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("blog_preflight_integrity", PREFLIGHT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blog_preflight_integrity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _review(nonce: str) -> str:
    return (
        "### Overall Score: 92/100 - Strong\n\n"
        f"Nonce: {nonce}\n\n"
        "zero P0 issues found\n"
        "BLOCKING: false (cleared all gates)\n"
    )


def _draft(tmp_path: Path) -> Path:
    draft = tmp_path / "post"
    draft.mkdir()
    (draft / "post.md").write_text("# Bai\n\nNoi dung ban dau.\n", encoding="utf-8")
    return draft


def _gate4(pf, draft, monkeypatch):
    # Isolate the provenance logic from the analyzer.
    monkeypatch.setattr(pf, "draft_score_check",
                        lambda d: {"checked": True, "violations": [], "warnings": [], "summary": None})
    return pf.gate_4_content_review(draft)


def test_init_records_markdown_hash(pf, tmp_path):
    draft = _draft(tmp_path)
    pf._init_review_nonce(draft)
    state = json.loads(pf._review_state_path(draft).read_text(encoding="utf-8"))
    assert state["draft_md_sha256"] == pf._draft_markdown_sha256(draft)
    assert len(state["draft_md_sha256"]) == 64


def test_unchanged_draft_passes(pf, tmp_path, monkeypatch):
    draft = _draft(tmp_path)
    nonce = pf._init_review_nonce(draft)
    (draft / "review.md").write_text(_review(nonce), encoding="utf-8")
    result = _gate4(pf, draft, monkeypatch)
    assert result["passed"] is True, result


def test_draft_edited_after_review_blocks(pf, tmp_path, monkeypatch):
    draft = _draft(tmp_path)
    nonce = pf._init_review_nonce(draft)
    (draft / "review.md").write_text(_review(nonce), encoding="utf-8")
    (draft / "post.md").write_text("# Bai\n\nDa sua sau review.\n", encoding="utf-8")
    result = _gate4(pf, draft, monkeypatch)
    assert result["passed"] is False
    assert any("Bài đã bị sửa sau khi review" in v and "blog-reviewer" in v
               for v in result["violations"])


def test_reissuing_nonce_after_edit_passes_again(pf, tmp_path, monkeypatch):
    draft = _draft(tmp_path)
    pf._init_review_nonce(draft)
    (draft / "post.md").write_text("# Bai\n\nSua.\n", encoding="utf-8")
    nonce = pf._init_review_nonce(draft)
    (draft / "review.md").write_text(_review(nonce), encoding="utf-8")
    assert _gate4(pf, draft, monkeypatch)["passed"] is True


def test_editing_review_md_alone_does_not_trip_the_hash(pf, tmp_path, monkeypatch):
    draft = _draft(tmp_path)
    nonce = pf._init_review_nonce(draft)
    (draft / "review.md").write_text(_review(nonce) + "\n", encoding="utf-8")
    assert _gate4(pf, draft, monkeypatch)["passed"] is True


def test_state_without_hash_warns_not_blocks(pf, tmp_path, monkeypatch):
    draft = _draft(tmp_path)
    nonce = "b" * 32
    pf._atomic_write_json(pf._review_state_path(draft),
                          {"draft": str(draft.resolve()), "nonce": nonce, "version": "old"})
    (draft / "review.md").write_text(_review(nonce), encoding="utf-8")
    (draft / "post.md").write_text("# Bai\n\nKhac.\n", encoding="utf-8")
    result = _gate4(pf, draft, monkeypatch)
    assert result["passed"] is True
    assert any("mã băm" in w for w in result["warnings"])


# ---- reserved hosts ------------------------------------------------------

@pytest.mark.parametrize("host", [
    "example.com", "example.net", "example.org", "example.vn", "www.example.vn",
    "foo.example", "a.test", "x.invalid", "localhost", "blog.localhost",
])
def test_reserved_hosts_are_placeholders(pf, host):
    assert pf._is_placeholder_url(f"https://{host}/bai") is True


@pytest.mark.parametrize("host", ["examples.vn", "myexample.vn", "cafe.vn", "contest.vn", "example-shop.vn"])
def test_real_hosts_are_not_placeholders(pf, host):
    assert pf._is_placeholder_url(f"https://{host}/bai") is False


def _gate5_draft(tmp_path: Path, canonical: str) -> Path:
    (tmp_path / "post.md").write_text("---\ntitle: x\n---\nbody\n", encoding="utf-8")
    (tmp_path / "post.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "post.html").write_text(
        '<!DOCTYPE html><html><head>'
        f'<link rel="canonical" href="{canonical}">'
        '<meta property="og:image" content="hero.png">'
        '<script type="application/ld+json">'
        '{"@type":"BlogPosting","headline":"x","image":"hero.png",'
        '"datePublished":"2026-07-09","author":{"name":"x"},"wordCount":1}'
        '</script></head><body><article>word</article></body></html>',
        encoding="utf-8",
    )
    return tmp_path


def test_gate5_placeholder_canonical_warns_without_allowlist(pf, tmp_path, monkeypatch):
    draft = _gate5_draft(tmp_path, "https://example.vn/bai")

    def boom(*a, **k):
        raise AssertionError("network must not be touched for a placeholder canonical")
    monkeypatch.setattr(pf, "_http_head", boom)
    result = pf.gate_5_asset_link_integrity(draft)
    assert not any("canonical" in v for v in result["violations"]), result["violations"]
    assert any("canonical đang là địa chỉ tạm, thay bằng URL thật trước khi đăng" in w
               for w in result["warnings"])


def test_gate5_ignores_allowlist_entry_for_reserved_host(pf, tmp_path):
    draft = _gate5_draft(tmp_path, "https://example.vn/bai")
    (draft / "preflight-allowlist.json").write_text(
        json.dumps({"unreachable_hosts": ["example.vn"]}), encoding="utf-8")
    assert "example.vn" not in pf._load_unreachable_allowlist(draft)
    result = pf.gate_5_asset_link_integrity(draft)
    assert any(w.startswith("info:") and "example.vn" in w for w in result["warnings"])
    assert any("địa chỉ tạm" in w for w in result["warnings"])


def test_gate5_real_canonical_has_no_placeholder_warning(pf, tmp_path):
    draft = _gate5_draft(tmp_path, "https://cafe-nha-minh.vn/bai")
    result = pf.gate_5_asset_link_integrity(draft)
    assert not any("địa chỉ tạm" in w for w in result["warnings"])


# ---- publish_cms ---------------------------------------------------------

def test_publish_refuses_placeholder_canonical_even_in_dry_run(tmp_path, capsys):
    import publish_cms
    sys.path.insert(0, str(Path(__file__).parent))
    from test_publish_cms import POST_MD
    draft = tmp_path / "cach-chon-may-pha-ca-phe"
    draft.mkdir()
    (draft / "cach-chon-may-pha-ca-phe.md").write_text(
        (POST_MD % {"extra": ""}).replace("cafe-nha-minh.vn", "example.vn"), encoding="utf-8")
    (draft / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    code = publish_cms.main(["--draft", str(draft), "--dry-run"])
    out = capsys.readouterr()
    text = out.out + out.err
    assert code == 2
    assert "canonical đang là địa chỉ tạm" in text and "Thay bằng URL thật" in text


def test_reserved_host_configured_as_a_site_is_not_a_placeholder(pf, tmp_path, monkeypatch):
    site = tmp_path / "sites" / "shop.test"
    site.mkdir(parents=True)
    (site / "site.toml").write_text('base_url = "https://shop.test"\n', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "sites"))
    assert pf._is_placeholder_url("https://shop.test/bai") is False
    assert pf._is_placeholder_url("https://other.test/bai") is True
