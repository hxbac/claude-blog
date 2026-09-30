"""Phase J item 2: vi_profile.py is the only place Vietnamese lexical tells live.

Finding A2: three hand-maintained lists (vi_prose AI_TELLS, vi_profile
ai_phrases, claude-seo _REPLACEMENTS_VI) in two repositories that already
disagreed. Now vi_profile.VI_TELLS is the list, everything else reads it, and
claude-seo gets a generated copy that a test compares.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ai_structure
import analyze_blog
import sync_vi_tells
import vi_profile
import vi_prose

SEO_COPY = ROOT.parent / "claude-seo" / "scripts" / "vi_tells_generated.py"


class TestEveryConsumerReadsTheProfile:
    def test_vi_prose_ai_tells_is_the_profile_formula_table(self):
        assert vi_prose.AI_TELLS is vi_profile.FORMULA_TELLS

    def test_profile_lists_are_views_of_vi_tells(self):
        profile = analyze_blog.LANGUAGE_PROFILES["vi"]
        assert profile["ai_phrases"] == tuple(
            t.text for t in vi_profile.VI_TELLS if t.tier == vi_profile.PHRASE)
        assert profile["ai_trigger_words"] == tuple(
            t.text for t in vi_profile.VI_TELLS if t.tier == vi_profile.TRIGGER)
        assert profile["ai_advisory_phrases"] == tuple(
            t.text for t in vi_profile.VI_TELLS if t.tier == vi_profile.ADVISORY)

    def test_ai_structure_reads_residue_and_closers_from_the_profile(self):
        assert ai_structure._CHATBOT_RESIDUE["vi"] == vi_profile.residue_patterns(preamble=False)
        assert ai_structure._CHATBOT_PREAMBLE["vi"] == vi_profile.residue_patterns(preamble=True)
        assert ai_structure._CLOSER_PHRASES["vi"] == vi_profile.closer_patterns()

    def test_no_other_script_carries_a_vietnamese_tell_literal(self):
        sentinels = ("không thể phủ nhận", "thời đại số", "chúc bạn thành công",
                     "hy vọng bài viết", "vô cùng quan trọng", "chìa khóa thành công")
        allowed = {"vi_profile.py"}
        offenders = []
        for path in SCRIPTS.glob("*.py"):
            if path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8").lower()
            offenders += [f"{path.name}: {s}" for s in sentinels if s in text]
        assert offenders == []

    def test_every_tell_regex_compiles_and_ids_are_unique(self):
        ids = [t.id for t in vi_profile.VI_TELLS]
        assert len(ids) == len(set(ids))
        for t in vi_profile.VI_TELLS:
            re.compile(vi_profile.tell_regex(t))

    def test_scored_and_advisory_tiers_are_disjoint(self):
        scored = {t.text for t in vi_profile.VI_TELLS if t.tier in (vi_profile.PHRASE, vi_profile.TRIGGER)}
        advisory = {t.text for t in vi_profile.VI_TELLS if t.tier == vi_profile.ADVISORY}
        assert scored.isdisjoint(advisory)


class TestScanner:
    def test_overlapping_matches_keep_only_the_longest(self):
        hits = vi_profile.scan_tells("Không thể phủ nhận rằng tốc độ quan trọng.")
        assert len(hits) == 1
        assert hits[0]["match"].lower() == "không thể phủ nhận rằng"

    def test_both_spellings_of_so_hoa_match(self):
        for text in ("Trong thời đại số hóa", "Trong thời đại số hoá"):
            assert vi_profile.scan_tells(text)

    def test_advisory_phrases_are_not_scored(self):
        assert vi_profile.scan_tells("Máy pha cà phê đã và đang được dùng nhiều.") == []

    def test_line_numbers_are_reported(self):
        hits = vi_profile.scan_tells("Dòng một.\nDòng hai.\nChúc bạn thành công!")
        assert hits[0]["line"] == 3

    def test_the_two_hy_vong_spellings_are_one_tell_family(self):
        # A2: vi_prose knew "hy vọng bài viết này sẽ hữu ích", the humanizer only
        # "hy vọng bài viết đã mang đến". Both are found now.
        for text in ("Hy vọng bài viết này sẽ hữu ích cho bạn.", "Hy vọng bài viết đã mang đến giá trị."):
            assert vi_profile.scan_tells(text)


class TestPreambleResidue:
    def test_duoi_day_la_is_residue_only_as_the_first_prose_line(self):
        first = "# Tiêu đề\n\nDưới đây là bài viết về máy pha cà phê.\n"
        later = "# Tiêu đề\n\nMáy pha có hai loại.\n\nDưới đây là ba tiêu chí chọn máy.\n"
        assert "chatbot_residue" in {f["check"] for f in ai_structure.analyze(first, "vi")["findings"]}
        assert "chatbot_residue" not in {f["check"] for f in ai_structure.analyze(later, "vi")["findings"]}

    def test_frontmatter_is_not_the_first_prose_line(self):
        text = "---\ntitle: x\nlang: vi\n---\n\n# Tiêu đề\n\nDưới đây là bài viết.\n"
        assert "chatbot_residue" in {f["check"] for f in ai_structure.analyze(text, "vi")["findings"]}

    def test_strong_residue_counts_anywhere(self):
        text = "# T\n\nĐoạn một.\n\nChắc chắn rồi, mình sẽ viết tiếp.\n"
        assert "chatbot_residue" in {f["check"] for f in ai_structure.analyze(text, "vi")["findings"]}


class TestGeneratedCopyForClaudeSeo:
    def test_generated_header_says_do_not_edit(self):
        text = sync_vi_tells.render()
        assert text.startswith("# GENERATED FILE. DO NOT EDIT.")
        assert "vi_profile.py" in text.splitlines()[2]

    def test_recorded_hash_matches_the_body(self):
        text = sync_vi_tells.render()
        recorded, body = sync_vi_tells.split_generated(text)
        assert recorded == hashlib.sha256(body.encode("utf-8")).hexdigest()

    def test_rewrite_table_comes_from_the_profile(self):
        ns: dict = {}
        exec(compile(sync_vi_tells.render(), "vi_tells_generated.py", "exec"), ns)
        assert ns["VI_REWRITES"] == vi_profile.rewrite_table()
        assert len(ns["VI_TELLS_DATA"]) == len(vi_profile.VI_TELLS)

    def test_generation_is_deterministic(self):
        assert sync_vi_tells.render() == sync_vi_tells.render()

    def test_write_then_check_round_trip(self, tmp_path):
        target = tmp_path / "vi_tells_generated.py"
        assert sync_vi_tells.main(["--write", "--target", str(target)]) == 0
        assert sync_vi_tells.main(["--check", "--target", str(target)]) == 0
        target.write_text(target.read_text(encoding="utf-8") + "\n# hand edit\n", encoding="utf-8")
        assert sync_vi_tells.main(["--check", "--target", str(target)]) == 1

    def test_missing_target_fails_the_check(self, tmp_path):
        assert sync_vi_tells.main(["--check", "--target", str(tmp_path / "nope.py")]) == 1

    @pytest.mark.skipif(not SEO_COPY.parent.is_dir(), reason="claude-seo checkout not next to claude-blog")
    def test_claude_seo_copy_is_in_sync(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "sync_vi_tells.py"), "--check"],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, proc.stderr
