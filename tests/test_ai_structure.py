"""Tests for scripts/ai_structure.py, the structural AI-writing tell detector.

Each check must fire on a crafted positive and stay silent on a crafted
negative (per PHASE-G-VIETNAMESE-PARITY.md's G4 verification bar). The
cluster score must rise when several distinct tells share one section, and
the module must never claim to detect AI authorship, only patterns.

Stdlib + pytest only. No network.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ai_structure.py"


def _import_module():
    spec = importlib.util.spec_from_file_location("ai_structure", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


MOD = _import_module()


def _run_cli(tmp_path: Path, text: str, lang: str = "en", fmt: str = "json"):
    f = tmp_path / "doc.md"
    f.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(f), "--lang", lang, "--format", fmt],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    if fmt == "json":
        return json.loads(result.stdout)
    return result.stdout


# ---------------------------------------------------------------------------
# Advisory framing: never a verdict
# ---------------------------------------------------------------------------


def test_report_never_claims_authorship_detection():
    report = MOD.analyze("# Title\n\nJust an ordinary sentence about nothing special.\n", "en")
    blob = json.dumps(report).lower()
    assert "not a verdict" in blob or "signal" in blob
    assert "detect ai authorship" not in blob.replace("does not claim to detect ai authorship", "")
    # The note explicitly disclaims authorship detection.
    assert "authorship" in report["note"].lower()


def test_docstring_carries_attribution():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Siqi Chen" in text
    assert "MIT" in text
    assert "Wikipedia" in text
    assert "CC BY-SA" in text


# ---------------------------------------------------------------------------
# Item 2: one-line closer
# ---------------------------------------------------------------------------


def test_one_line_closer_fires_on_phrase_match():
    text = (
        "# Title\n\n"
        "Caching cuts repeat work and avoids duplicated queries on every page load.\n\n"
        "That is the real win.\n"
    )
    report = MOD.analyze(text, "en")
    checks = {f["check"] for f in report["findings"]}
    assert "one_line_closer" in checks


def test_one_line_closer_fires_on_vietnamese_phrase_match():
    text = (
        "# Tieu de\n\n"
        "Uống đủ nước mỗi ngày giúp cơ thể khỏe mạnh hơn theo nhiều cách khác nhau.\n\n"
        "Đó chính là mấu chốt.\n"
    )
    report = MOD.analyze(text, "vi")
    checks = {f["check"] for f in report["findings"]}
    assert "one_line_closer" in checks


def test_one_line_closer_silent_on_unrelated_short_paragraph():
    text = (
        "# Title\n\n"
        "The team shipped the release on schedule after two weeks of testing.\n\n"
        "Meanwhile, the support queue stayed quiet all week.\n"
    )
    report = MOD.analyze(text, "en")
    checks = {f["check"] for f in report["findings"]}
    assert "one_line_closer" not in checks


# ---------------------------------------------------------------------------
# Item 6: forced triads (document-wide threshold)
# ---------------------------------------------------------------------------


def test_forced_triad_needs_three_to_fire():
    one_triad = (
        "# Title\n\n"
        "The event includes talks, panels, and workshops for every attendee here today.\n"
    )
    report = MOD.analyze(one_triad, "en")
    assert "forced_triad" not in {f["check"] for f in report["findings"]}

    three_triads = (
        "# Title\n\n"
        "The plan covers speed, cost, and quality for every team involved today.\n"
        "The team values honesty, patience, and rigor above everything else at work.\n"
        "The offer includes coffee, snacks, and water for every visitor who attends.\n"
    )
    report2 = MOD.analyze(three_triads, "en")
    assert "forced_triad" in {f["check"] for f in report2["findings"]}
    assert sum(1 for f in report2["findings"] if f["check"] == "forced_triad") == 3


def test_forced_triad_vietnamese_conjunction():
    text = (
        "# Tieu de\n\n"
        "Khóa học gồm lý thuyết, thực hành, và kiểm tra dành cho học viên mới.\n"
        "Chương trình có tốc độ, chi phí, và chất lượng cho mọi khách hàng ở đây.\n"
        "Gói dịch vụ có tư vấn, triển khai, và bảo trì cho toàn bộ hệ thống.\n"
    )
    report = MOD.analyze(text, "vi")
    assert "forced_triad" in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 7: repeated sentence openings
# ---------------------------------------------------------------------------


def test_repeated_openings_fires_on_three_consecutive():
    text = (
        "# Title\n\n"
        "She noted the door. She noted the lock on it. She filed both away quickly.\n"
    )
    report = MOD.analyze(text, "en")
    assert "repeated_openings" in {f["check"] for f in report["findings"]}


def test_repeated_openings_silent_on_two_consecutive():
    text = (
        "# Title\n\n"
        "She noted the door. She noted the lock. Then she left the building for good.\n"
    )
    report = MOD.analyze(text, "en")
    assert "repeated_openings" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 19: bold as decoration
# ---------------------------------------------------------------------------


def test_bold_list_labels_fires_on_three_consecutive_labeled_items():
    text = (
        "# Title\n\n"
        "- **Speed:** the app loads quickly on most connections.\n"
        "- **Cost:** the plan stays under budget for most teams.\n"
        "- **Support:** responses arrive within one business day.\n"
    )
    report = MOD.analyze(text, "en")
    assert "bold_decoration" in {f["check"] for f in report["findings"]}


def test_bold_silent_on_single_bold_word():
    text = "# Title\n\nThis is **important** but otherwise ordinary prose about the topic.\n"
    report = MOD.analyze(text, "en")
    assert "bold_decoration" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 20: decorative headings, English only
# ---------------------------------------------------------------------------


def test_decorative_headings_fires_on_title_case_en():
    text = (
        "# The Complete Guide To Better Sleep\n\n"
        "text\n\n"
        "## Why Sleep Matters A Lot\n\n"
        "text\n\n"
        "## Final Thoughts And Next Steps\n\n"
        "text\n"
    )
    report = MOD.analyze(text, "en")
    assert "decorative_headings" in {f["check"] for f in report["findings"]}


def test_decorative_headings_silent_on_sentence_case_en():
    text = (
        "# A complete guide to better sleep\n\n"
        "text\n\n"
        "## Why sleep matters a lot\n\n"
        "text\n\n"
        "## Final thoughts and next steps\n\n"
        "text\n"
    )
    report = MOD.analyze(text, "en")
    assert "decorative_headings" not in {f["check"] for f in report["findings"]}


def test_decorative_headings_is_a_noop_for_vietnamese():
    text = (
        "# Huong Dan Ngu Ngon\n\n"
        "text\n\n"
        "## Tai Sao Giac Ngu Quan Trong\n\n"
        "text\n\n"
        "## Ket Luan Va Buoc Tiep Theo\n\n"
        "text\n"
    )
    report = MOD.analyze(text, "vi")
    assert "decorative_headings" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 21: curly quotes
# ---------------------------------------------------------------------------


def test_curly_quotes_detected_and_marked_weak_alone():
    text = "# Title\n\nHe said “it works” well enough for now.\n"
    report = MOD.analyze(text, "en")
    hits = [f for f in report["findings"] if f["check"] == "curly_quotes"]
    assert len(hits) == 1
    assert hits[0]["weak_alone"] is True


def test_straight_quotes_do_not_trigger():
    text = '# Title\n\nHe said "it works" well enough for now.\n'
    report = MOD.analyze(text, "en")
    assert "curly_quotes" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 24: heading echoed in its own first sentence
# ---------------------------------------------------------------------------


def test_heading_echo_fires_when_first_sentence_restates_heading():
    text = "## Performance\n\nPerformance matters here.\n\nWhen users hit a slow page, they leave immediately.\n"
    report = MOD.analyze(text, "en")
    assert "heading_echoed" in {f["check"] for f in report["findings"]}


def test_heading_echo_silent_when_first_sentence_adds_content():
    text = (
        "## Performance\n\n"
        "Slow pages lose visitors within the first few seconds of a session.\n"
    )
    report = MOD.analyze(text, "en")
    assert "heading_echoed" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Item 22: chatbot residue
# ---------------------------------------------------------------------------


def test_chatbot_residue_english():
    text = "# Title\n\nCertainly! Here is the summary you asked for about the release.\n"
    report = MOD.analyze(text, "en")
    assert "chatbot_residue" in {f["check"] for f in report["findings"]}


def test_chatbot_residue_vietnamese():
    text = "# Tieu de\n\nDưới đây là phần tóm tắt về nội dung chính của bài viết.\n"
    report = MOD.analyze(text, "vi")
    assert "chatbot_residue" in {f["check"] for f in report["findings"]}


def test_chatbot_residue_silent_on_ordinary_prose():
    text = "# Title\n\nThe release shipped on schedule after two weeks of testing.\n"
    report = MOD.analyze(text, "en")
    assert "chatbot_residue" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Code fences and inline code are never scanned
# ---------------------------------------------------------------------------


def test_code_fence_is_not_scanned():
    text = (
        "# Title\n\n"
        "```\n"
        "He said “it works” well. That is the real win.\n"
        "```\n\n"
        "Ordinary prose follows with no tells in it at all today.\n"
    )
    report = MOD.analyze(text, "en")
    assert report["finding_count"] == 0


def test_inline_code_span_is_not_scanned():
    text = "# Title\n\nRun `echo “hello”` in your shell to test the command.\n"
    report = MOD.analyze(text, "en")
    assert "curly_quotes" not in {f["check"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# Cluster score: the number that actually matters
# ---------------------------------------------------------------------------


def test_cluster_score_rises_when_tells_share_a_section():
    lone_tell = "# Title\n\nHe said “it works” well enough for everyone involved.\n"
    report = MOD.analyze(lone_tell, "en")
    assert report["cluster_score"] == 1

    heavy_section = (
        "# Title\n\n"
        "## Why Sleep Matters\n\n"
        "The plan covers speed, cost, and quality for every team here today.\n"
        "The team values honesty, patience, and rigor above everything at work.\n"
        "The offer includes coffee, snacks, and water for every visitor who comes.\n\n"
        "She checked the door. She checked the window. She checked the lock twice.\n\n"
        "That is the real win.\n"
    )
    report2 = MOD.analyze(heavy_section, "en")
    assert report2["cluster_score"] >= 3
    top = report2["sections"][0]
    assert top["cluster_score"] == report2["cluster_score"]
    assert len(top["tells"]) == top["cluster_score"]


def test_single_tell_alone_is_low_cluster_score():
    text = "# Title\n\nHe said “it works” well enough for everyone involved today.\n"
    report = MOD.analyze(text, "en")
    assert report["finding_count"] == 1
    assert report["cluster_score"] == 1


def test_clean_human_text_stays_quiet():
    text = (
        "# How I picked my first mechanical keyboard\n\n"
        "I used a cheap membrane board for years without thinking about it much.\n"
        "A coworker lent me a mechanical one for a couple of days last spring.\n\n"
        "## What changed my mind\n\n"
        "Typing felt different, and my fingers were less tired by the end of the day.\n"
        "The clicking bothered me at first, but I got used to it within a week or so.\n"
        "Budget mattered most, since a good board is not cheap around here.\n"
        "I ended up with a quiet board that works fine in a shared office.\n"
    )
    report = MOD.analyze(text, "en")
    assert report["finding_count"] == 0
    assert report["cluster_score"] == 0


def test_clean_vietnamese_text_stays_quiet():
    text = (
        "# Cách tôi chọn bàn phím cơ đầu tiên\n\n"
        "Tôi từng dùng bàn phím màng cao su suốt nhiều năm mà không để ý gì.\n"
        "Một đồng nghiệp cho tôi mượn bàn phím cơ để dùng thử trong vài ngày.\n\n"
        "## Những thứ tôi cân nhắc trước khi mua\n\n"
        "Cảm giác gõ khác hẳn, ngón tay đỡ mỏi hơn hẳn so với trước đây.\n"
        "Tiếng lách cách hơi khó chịu lúc đầu, nhưng tôi quen dần sau một tuần.\n"
        "Ngân sách vẫn là yếu tố quan trọng vì bàn phím tốt không hề rẻ.\n"
        "Cuối cùng tôi chọn một chiếc bàn phím vừa đủ yên tĩnh cho phòng chung.\n"
    )
    report = MOD.analyze(text, "vi")
    assert report["finding_count"] == 0
    assert report["cluster_score"] == 0


# ---------------------------------------------------------------------------
# Dash check is referenced, not duplicated
# ---------------------------------------------------------------------------


def test_dash_check_is_not_implemented_here():
    text = "# Title\n\nA sentence with an em dash " + chr(0x2014) + " right here in the middle.\n"
    report = MOD.analyze(text, "en")
    assert "dash" not in {f["check"] for f in report["findings"]}
    assert "lint_prose.py" in report["dash_check"]


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


def test_cli_json_output(tmp_path: Path):
    report = _run_cli(tmp_path, "# Title\n\nOrdinary sentence with nothing unusual in it today.\n")
    assert report["ok"] is True
    assert report["lang"] == "en"


def test_cli_text_output(tmp_path: Path):
    out = _run_cli(
        tmp_path,
        "# Title\n\nHe said “it works” well enough for everyone involved today.\n",
        fmt="text",
    )
    assert "curly_quotes" in out
    assert "lint_prose.py" in out


def test_cli_stdin(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-", "--format", "json"],
        input="# Title\n\nOrdinary sentence with nothing unusual in it today.\n",
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["ok"] is True


def test_cli_missing_file_errors_cleanly(tmp_path: Path):
    missing = tmp_path / "nope.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(missing)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "Error" in result.stderr



class TestVietnameseCorrelativeFrame:
    """Humanizer item 1 is judgement only in English because English says it a
    dozen ways. Vietnamese uses a small set of fixed correlative frames, so the
    same pattern is mechanically detectable in this language.
    """

    def _scan(self, body):
        return MOD.analyze("# Thu\n\n" + body, lang="vi")

    def test_one_occurrence_stays_quiet(self):
        result = self._scan("Dịch vụ này không chỉ nhanh mà còn rẻ.\n")
        assert [f for f in result["findings"] if f["check"] == "not_x_but_y"] == []

    def test_several_occurrences_report(self):
        result = self._scan(
            "Dịch vụ này không chỉ nhanh mà còn rẻ.\n\n"
            "Đây không phải là chi phí mà là khoản đầu tư.\n\n"
            "Sản phẩm không những bền mà còn đẹp.\n"
        )
        hits = [f for f in result["findings"] if f["check"] == "not_x_but_y"]
        assert len(hits) == 3
        assert all(f["weak_alone"] for f in hits)

    def test_english_is_not_scanned_for_this_frame(self):
        result = MOD.analyze(
            "# Test\n\nIt is not just fast but also cheap.\n\n"
            "This is not a cost but an investment.\n",
            lang="en",
        )
        assert [f for f in result["findings"] if f["check"] == "not_x_but_y"] == []


class TestVietnameseCloserIntensifier:
    """A stock closer stays a stock closer when an intensifier is dropped in.

    Found by running the detector on a hand written sample that closed with
    "do moi chinh la mau chot". The bare pattern missed it, and the inflated
    variant is the one a model actually reaches for.
    """

    def _closer(self, closing_line):
        body = (
            "# Thu\n\n"
            "Chi phí vận chuyển thường cao hơn bảng giá vì phí hoàn hàng "
            "được tính cả hai chiều cho mỗi đơn.\n\n" + closing_line + "\n"
        )
        result = MOD.analyze(body, lang="vi")
        return [f for f in result["findings"] if f["check"] == "one_line_closer"]

    def test_bare_form(self):
        assert self._closer("Đó chính là mấu chốt.")

    def test_with_intensifier(self):
        assert self._closer("Đó mới chính là mấu chốt.")

    def test_with_stacked_intensifiers(self):
        assert self._closer("Đó mới thực sự là mấu chốt.")

    def test_ordinary_short_sentence_is_not_a_closer(self):
        assert not self._closer("Tôi đã đổi sang đơn vị khác từ tháng ba.")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
