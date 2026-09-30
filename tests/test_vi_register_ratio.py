"""Phase J item 1: one register implementation, with the ratio rule.

Findings A1 and A2 of docs/review/01-findings.md: the old checkers flagged
ordinary human Vietnamese (an author called "Lan Anh", "anh thợ mộc", a quoted
"quý khách") and disagreed with each other. There is now one implementation
(vi_register.py), vi_prose.py imports it, and a minority register is drift only
at max(15% of marked sentences, 3 sentences).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import vi_prose
import vi_register

FIXTURES = Path(__file__).parent / "fixtures"


def _post(body: str, author: str = "Lan Anh") -> str:
    return f'---\ntitle: "Bài thử"\nauthor: "{author}"\nlang: vi\n---\n\n{body}\n'


class TestHumanSampleIsClean:
    """The review's human sample (reconstructed: the original was not kept)."""

    def setup_method(self):
        self.raw = (FIXTURES / "vi_human_review_sample.md").read_text(encoding="utf-8")

    def test_register_checker_reports_zero_findings(self):
        result = vi_register.analyze_register(self.raw)
        assert result["consistent"] is True
        assert result["off_register"] == []
        assert result["tolerated"] == []
        assert result["dominant_register"] == "peer"

    def test_prose_linter_reports_zero_findings(self):
        report = vi_prose.lint_text(self.raw)
        assert report["findings"] == []

    def test_prose_linter_cli_exits_zero(self):
        script = Path(__file__).parent.parent / "scripts" / "vi_prose.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(FIXTURES / "vi_human_review_sample.md")],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, proc.stdout
        assert "PASS" in proc.stdout

    def test_fixture_contains_every_trap_of_the_original(self):
        # The traps must stay in the fixture or the test proves nothing.
        assert 'author: "Lan Anh"' in self.raw
        assert "Anh thợ mộc" in self.raw
        assert "chị khách" in self.raw
        assert '"quý khách"' in self.raw


class TestWhatIsStripped:
    def test_frontmatter_author_is_not_a_pronoun(self):
        result = vi_register.analyze_register(_post("Bạn nên đo lại. Mình cũng làm vậy."))
        assert result["sentence_counts"]["polite"] == 0

    def test_bare_anh_and_chi_are_dropped(self):
        text = "Anh thợ mộc báo giá cao. Chị khách hỏi lại. Anh ấy đồng ý ngay."
        result = vi_register.analyze_register(text)
        assert result["marker_counts"] == {"peer": 0, "polite": 0, "formal": 0}

    def test_anh_chi_address_forms_are_kept(self):
        result = vi_register.analyze_register("Anh chị nên đo lại. Các anh chị cứ hỏi thêm.")
        assert result["sentence_counts"]["polite"] == 2

    def test_anh_chi_em_is_kinship_not_address(self):
        result = vi_register.analyze_register("Anh chị em trong nhà thường ăn tối cùng nhau.")
        assert result["marker_counts"]["polite"] == 0

    def test_reflexive_minh_is_not_the_peer_pronoun(self):
        result = vi_register.analyze_register("Cô ấy sống một mình. Anh ta tự mình sửa lấy.")
        assert result["marker_counts"]["peer"] == 0

    def test_quoted_span_is_not_an_address(self):
        text = 'Bạn hỏi "quý khách" nghĩa là gì. Câu "quý vị nên đọc kỹ" là lời chào của cửa hàng.'
        result = vi_register.analyze_register(text)
        assert result["sentence_counts"]["formal"] == 0

    def test_curly_and_guillemet_quotes_are_stripped(self):
        result = vi_register.analyze_register("Mình nhớ câu “quý khách vui lòng đợi” và «quý vị» nữa.")
        assert result["sentence_counts"]["formal"] == 0

    def test_code_fence_blockquote_and_inline_code_are_stripped(self):
        text = (
            "Bạn nên đo lại.\n\n```\nQuý khách vui lòng đợi.\n```\n\n"
            "> Quý khách sẽ nhận hàng sau ba ngày.\n\n"
            "Ghi `Quý vị` trong ô tên."
        )
        result = vi_register.analyze_register(text)
        assert result["sentence_counts"]["formal"] == 0
        assert result["sentence_counts"]["peer"] == 1

    def test_line_numbers_survive_stripping(self):
        text = _post("Bạn nên đo lại.\n\nQuý khách vui lòng đợi.")
        # frontmatter is 5 lines (--- x4 + ---), blank, body at line 7 and 9
        rows = vi_register.analyze_register(text)["tolerated"]
        assert [r["line"] for r in rows] == [9]


class TestRatioRule:
    def test_threshold_is_the_larger_of_fifteen_percent_and_three(self):
        assert vi_register.drift_threshold(5) == 3
        assert vi_register.drift_threshold(20) == 3
        assert vi_register.drift_threshold(21) == 4   # ceil(3.15)
        assert vi_register.drift_threshold(100) == 15

    def test_stray_quote_free_aside_in_a_long_peer_post_is_tolerated(self):
        peer = " ".join(f"Bạn nên kiểm tra mục {i}." for i in range(1, 21))
        result = vi_register.analyze_register(peer + " Quý khách hãy thử.")
        assert result["consistent"] is True
        assert len(result["tolerated"]) == 1

    def test_two_off_register_sentences_stay_below_the_three_sentence_floor(self):
        text = "Bạn nên đo. Bạn nên thử. Bạn nên xem. Quý khách hãy đợi. Quý vị nên đọc."
        assert vi_register.analyze_register(text)["consistent"] is True

    def test_three_off_register_sentences_are_drift(self):
        text = ("Bạn nên đo. Bạn nên thử. Bạn nên xem. Bạn nên hỏi. "
                "Quý khách hãy đợi. Quý vị nên đọc. Quý khách sẽ nhận hàng.")
        result = vi_register.analyze_register(text)
        assert result["consistent"] is False
        assert result["drift_registers"] == ["formal"]

    def test_fifteen_percent_beats_three_on_a_long_post(self):
        peer = " ".join(f"Bạn nên kiểm tra mục {i}." for i in range(1, 25))
        formal = " Quý khách hãy đợi. Quý vị nên đọc. Quý khách sẽ nhận hàng."
        # 27 marked sentences: threshold ceil(4.05) = 5, so 3 formal are tolerated
        assert vi_register.analyze_register(peer + formal)["consistent"] is True

    def test_consistent_post_has_no_dominant_when_no_markers(self):
        assert vi_register.analyze_register("Trời mưa cả ngày.")["dominant_register"] is None


class TestOneImplementation:
    def test_vi_prose_imports_the_register_module(self):
        assert vi_prose.vi_register is vi_register

    def test_vi_prose_owns_no_register_sets(self):
        assert not hasattr(vi_prose, "REGISTER_SETS")

    def test_both_tools_agree_on_the_same_file(self):
        raw = (FIXTURES / "vi_slop_review_sample.md").read_text(encoding="utf-8")
        reg = vi_register.analyze_register(raw)
        prose = vi_prose.lint_text(raw)
        prose_drift = any(f["type"] == "register_drift" for f in prose["findings"])
        assert prose_drift == (not reg["consistent"])
        assert prose_drift is True

    def test_register_drift_finding_lists_the_lines_to_fix(self):
        raw = (FIXTURES / "vi_slop_review_sample.md").read_text(encoding="utf-8")
        finding = next(f for f in vi_prose.lint_text(raw)["findings"] if f["type"] == "register_drift")
        assert finding["severity"] == "P0"
        assert finding["lines"]
        assert "dòng" in finding["fix"]
