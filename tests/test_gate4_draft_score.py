"""Phase J item 5: Gate 4 is 'draft score >= 85 and zero P0'.

Gate 4 used to require a reviewer score of 90 on the published-page rubric.
That was structurally unreachable for a draft. Now both the reviewer's number
and the analyzer's own `--mode draft` run on the draft source must reach 85,
and any P0 blocks.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "scripts" / "blog_preflight.py"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def pf(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_BLOG_REVIEW_STATE_DIR", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("blog_preflight_gate4", PREFLIGHT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blog_preflight_gate4"] = mod
    spec.loader.exec_module(mod)
    return mod


def review(nonce: str, score: int = 92) -> str:
    return (
        "## Quality Review: Test\n\n"
        f"### Overall Score: {score}/100 - Strong\n\n"
        "zero P0 issues found\n\n"
        f"Nonce: {nonce}\n"
        "BLOCKING: false (cleared all gates)\n"
    )


def make_draft(tmp_path: Path, pf, fixture: str | None, score: int = 92) -> Path:
    draft = tmp_path / "post"
    draft.mkdir()
    nonce = "a" * 32
    (draft / "review.md").write_text(review(nonce, score), encoding="utf-8")
    pf._atomic_write_json(pf._review_state_path(draft),
                          {"draft": str(draft.resolve()), "nonce": nonce, "version": "test"})
    if fixture:
        shutil.copy(FIXTURES / fixture, draft / "post.md")
    return draft


def test_threshold_is_85(pf):
    assert pf.GATE4_MIN_SCORE == 85


def test_reviewer_score_of_85_passes_and_84_fails(tmp_path, pf):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ok = pf.gate_4_content_review(make_draft(tmp_path / "a", pf, None, 85))
    assert ok["passed"] is True
    bad = pf.gate_4_content_review(make_draft(tmp_path / "b", pf, None, 84))
    assert bad["passed"] is False
    assert any("below 85" in v for v in bad["violations"])


def test_human_draft_with_good_review_passes(tmp_path, pf):
    result = pf.gate_4_content_review(make_draft(tmp_path, pf, "vi_human_review_sample.md"))
    assert result["passed"] is True, result
    assert result["draft_score"]["ready"] is True


def test_slop_draft_is_blocked_even_when_the_reviewer_was_generous(tmp_path, pf):
    result = pf.gate_4_content_review(make_draft(tmp_path, pf, "vi_slop_review_sample.md", score=95))
    assert result["passed"] is False
    joined = " ".join(result["violations"])
    assert "thấp hơn ngưỡng 85" in joined      # Vietnamese message for a vi post
    assert "P0 register_drift" in joined
    assert "P0 chatbot_residue" in joined
    assert result["draft_score"]["p0_count"] >= 3


def test_p0_blocks_even_when_the_draft_number_is_high(tmp_path, pf, monkeypatch):
    import draft_rubric
    monkeypatch.setattr(draft_rubric, "legal_disclosure_p0",
                        lambda fm, body, lang: [{"code": "legal_disclosure", "message": "Thiếu khai báo."}])
    result = pf.gate_4_content_review(make_draft(tmp_path, pf, "vi_human_review_sample.md"))
    assert result["passed"] is False
    assert any("P0 legal_disclosure" in v for v in result["violations"])


def test_english_post_gets_an_english_score_message(tmp_path, pf):
    draft = make_draft(tmp_path, pf, None)
    (draft / "post.md").write_text(
        "---\ntitle: T\nlang: en\n---\n\n# T\n\n" + "Short thin note. " * 5, encoding="utf-8")
    result = pf.gate_4_content_review(draft)
    assert any("draft score" in v and "is below 85" in v for v in result["violations"])


def test_missing_draft_source_only_warns(tmp_path, pf):
    result = pf.gate_4_content_review(make_draft(tmp_path, pf, None))
    assert result["passed"] is True
    assert any("not machine-verified" in w for w in result["warnings"])


def test_two_markdown_files_are_ambiguous_and_warn(tmp_path, pf):
    draft = make_draft(tmp_path, pf, "vi_human_review_sample.md")
    (draft / "post.md").rename(draft / "first.md")
    shutil.copy(FIXTURES / "vi_real_post_kiem_soat.md", draft / "second.md")
    result = pf.gate_4_content_review(draft)
    assert any("more than one" in w for w in result["warnings"])


def test_review_md_is_never_mistaken_for_the_draft(tmp_path, pf):
    draft = make_draft(tmp_path, pf, None)
    path, note = pf._draft_markdown(draft)
    assert path is None and "no <slug>.md" in note


def test_analyzer_crash_is_a_violation_not_a_traceback(tmp_path, pf, monkeypatch):
    import analyze_blog
    def boom(*a, **k):
        raise RuntimeError("kaput")
    monkeypatch.setattr(analyze_blog, "analyze_file", boom)
    result = pf.gate_4_content_review(make_draft(tmp_path, pf, "vi_human_review_sample.md"))
    assert result["passed"] is False
    assert any("draft scoring failed" in v for v in result["violations"])
