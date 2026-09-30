"""Phase K: Vietnamese legal-disclosure checks, shared by Gate 4 and Gate 5,
and the YMYL author box in blog_render."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_blog
import blog_preflight
import blog_render
import draft_rubric
import vi_compliance

FIXTURES = Path(__file__).parent / "fixtures"
BASE = (FIXTURES / "vi_real_post_kiem_soat.md").read_text(encoding="utf-8")

TPCN_PARA = "\n\nNhiều người dùng thực phẩm chức năng bổ sung canxi mỗi ngày.\n"
DISCLAIMER = "\n\nSản phẩm này không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh.\n"


def codes(findings):
    return {f["code"] for f in findings}


def strip_diacritics(text: str) -> str:
    return vi_compliance.fold(text)


# --- the shared checker ------------------------------------------------------

class TestCheck:
    def test_no_keys_no_findings(self):
        assert vi_compliance.check({}, "Bài về thực phẩm chức năng.") == []

    def test_health_functional_food_without_disclaimer_is_blocked_with_exact_sentence(self):
        found = vi_compliance.check({"topic_class": "health"}, TPCN_PARA)
        assert codes(found) == {"legal_disclosure_functional_food"}
        msg = found[0]["message"]
        assert vi_compliance.FUNCTIONAL_FOOD_SENTENCE in msg
        assert "Thông tư 09/2015/TT-BYT" in msg and "thiếu" in msg

    def test_health_compliant_passes(self):
        assert vi_compliance.check({"topic_class": "health"}, TPCN_PARA + DISCLAIMER) == []

    def test_disclaimer_without_diacritics_passes(self):
        text = TPCN_PARA + strip_diacritics(DISCLAIMER)
        assert vi_compliance.check({"topic_class": "health"}, text) == []

    def test_trigger_without_diacritics_and_tpcn_abbreviation(self):
        for trigger in ("thuc pham chuc nang", "TPCN", "Thực Phẩm Bảo Vệ Sức Khỏe"):
            assert vi_compliance.check({"topic_class": "health"}, f"Dung {trigger} moi ngay.")

    def test_nfd_input_matches(self):
        nfd = unicodedata.normalize("NFD", "Dùng thực phẩm chức năng mỗi ngày.")
        assert vi_compliance.check({"topic_class": "health"}, nfd)

    def test_half_a_disclaimer_is_not_enough(self):
        text = TPCN_PARA + "\n\nSản phẩm này không phải là thuốc.\n"
        assert vi_compliance.check({"topic_class": "health"}, text)

    def test_functional_food_outside_health_is_not_checked(self):
        assert vi_compliance.check({"topic_class": "general"}, TPCN_PARA) == []
        assert vi_compliance.check({"topic_class": "cosmetics"}, TPCN_PARA) == []

    def test_health_without_functional_food_mention_passes(self):
        assert vi_compliance.check({"topic_class": "health"}, "Ngủ đủ giấc giúp tỉnh táo.") == []

    @pytest.mark.parametrize("value", ["true", "True", "yes", True])
    def test_sponsored_without_disclosure_blocked(self, value):
        found = vi_compliance.check({"sponsored": value}, "Máy pha cà phê này rất tốt.")
        assert codes(found) == {"legal_disclosure_sponsored"}
        assert vi_compliance.SPONSORED_SENTENCE in found[0]["message"]

    @pytest.mark.parametrize("value", ["false", "", "no", False])
    def test_falsey_sponsored_ignored(self, value):
        assert vi_compliance.check({"sponsored": value}, "Nội dung bất kỳ.") == []

    @pytest.mark.parametrize("line", [
        "Bài viết này là nội dung quảng cáo của Hãng X.",
        "Nội dung được tài trợ bởi Hãng X.",
        "Bai viet nay duoc tai tro boi Hang X.",
        "Sponsored by Hãng X.",
    ])
    def test_sponsored_disclosure_variants_pass(self, line):
        assert vi_compliance.check({"sponsored": "true"}, f"{line}\n\nThân bài.") == []

    def test_bare_word_quang_cao_is_not_a_disclosure(self):
        assert vi_compliance.check({"sponsored": "true"}, "Chạy quảng cáo Facebook cần ngân sách.")

    def test_affiliate_without_disclosure_blocked_and_with_passes(self):
        found = vi_compliance.check({"affiliate": "true"}, "Mua tại [đây](https://x.vn).")
        assert codes(found) == {"legal_disclosure_affiliate"}
        assert vi_compliance.AFFILIATE_SENTENCE in found[0]["message"]
        for ok in ("Bài viết có liên kết tiếp thị, có thể nhận hoa hồng.",
                   "Bai viet co lien ket tiep thi (affiliate).",
                   "This post has affiliate links."):
            assert vi_compliance.check({"affiliate": "true"}, ok) == []

    def test_sponsor_disclosure_does_not_satisfy_affiliate(self):
        fm = {"sponsored": "true", "affiliate": "true"}
        found = vi_compliance.check(fm, "Nội dung được tài trợ bởi Hãng X.")
        assert codes(found) == {"legal_disclosure_affiliate"}

    def test_parse_frontmatter(self):
        fm, body = vi_compliance.parse_frontmatter('---\nsponsored: "true"\ntopic_class: health\n---\nThân')
        assert fm == {"sponsored": "true", "topic_class": "health"} and body == "Thân"
        assert vi_compliance.parse_frontmatter("Không có") == ({}, "Không có")


# --- Gate 4 -----------------------------------------------------------------

def make_post(tmp_path: Path, extra_fm: str, addition: str) -> Path:
    fm_end = BASE.index("\n---", 3)
    text = BASE[:fm_end] + "\n" + extra_fm.strip("\n") + BASE[fm_end:] + addition
    path = tmp_path / "p.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestGate4:
    def p0(self, path):
        return {p["code"]: p for p in analyze_blog.analyze_file(str(path), "draft")["score"]["p0"]}

    def test_health_claim_without_disclaimer_is_p0_with_sentence(self, tmp_path):
        p0 = self.p0(make_post(tmp_path, "topic_class: health", TPCN_PARA))
        assert "legal_disclosure_functional_food" in p0
        assert vi_compliance.FUNCTIONAL_FOOD_SENTENCE in p0["legal_disclosure_functional_food"]["message"]

    def test_compliant_health_post_has_no_legal_p0(self, tmp_path):
        assert not [c for c in self.p0(make_post(tmp_path, "topic_class: health", TPCN_PARA + DISCLAIMER))
                    if c.startswith("legal")]

    def test_post_without_keys_unaffected(self, tmp_path):
        assert not [c for c in self.p0(make_post(tmp_path, "", TPCN_PARA)) if c.startswith("legal")]

    def test_gate4_and_hook_share_one_implementation(self):
        fm, body = {"sponsored": "true"}, "x"
        assert draft_rubric.legal_disclosure_p0(fm, body, "vi") == vi_compliance.check(fm, body)


# --- Gate 5 -----------------------------------------------------------------

def gate5_dir(tmp_path: Path, extra_fm: str, addition: str) -> Path:
    d = tmp_path / "post"
    d.mkdir()
    src = make_post(d, extra_fm, addition)
    src.rename(d / "post.md")
    return d


class TestGate5:
    def test_health_without_disclaimer_blocked_in_vietnamese(self, tmp_path):
        d = gate5_dir(tmp_path, "topic_class: health", TPCN_PARA)
        out = blog_preflight._compliance_check(d)
        assert len(out["violations"]) == 1
        assert vi_compliance.FUNCTIONAL_FOOD_SENTENCE in out["violations"][0]

    def test_compliant_passes(self, tmp_path):
        d = gate5_dir(tmp_path, "topic_class: health\nsponsored: true",
                      TPCN_PARA + DISCLAIMER + "\n\nNội dung được tài trợ bởi Hãng X.\n")
        assert blog_preflight._compliance_check(d)["violations"] == []

    def test_existing_post_unaffected(self, tmp_path):
        d = gate5_dir(tmp_path, "", TPCN_PARA)
        assert blog_preflight._compliance_check(d) == {"violations": [], "warnings": []}

    def test_gate5_reports_the_violation(self, tmp_path, monkeypatch):
        d = gate5_dir(tmp_path, "sponsored: true", "")
        (d / "post.html").write_text(
            '<!DOCTYPE html><html><head><link rel="canonical" href="https://example.com/p/">'
            "</head><body><article><p>Thân bài.</p></article></body></html>", encoding="utf-8")
        (d / "post.pdf").write_bytes(b"%PDF-1.4")
        result = blog_preflight.gate_5_asset_link_integrity(d, slug="post")
        assert any("sponsored: true" in v and vi_compliance.SPONSORED_SENTENCE in v
                   for v in result["violations"])
        assert result["passed"] is False

    def test_gate5_compliant_post_has_no_compliance_violation(self, tmp_path):
        d = gate5_dir(tmp_path, "sponsored: true", "\n\nNội dung được tài trợ bởi Hãng X.\n")
        (d / "post.html").write_text(
            '<!DOCTYPE html><html><head><link rel="canonical" href="https://example.com/p/">'
            "</head><body><article><p>Thân bài.</p></article></body></html>", encoding="utf-8")
        (d / "post.pdf").write_bytes(b"%PDF-1.4")
        result = blog_preflight.gate_5_asset_link_integrity(d, slug="post")
        assert not any("sponsored" in v for v in result["violations"])


# --- author box -------------------------------------------------------------

FM_BASE = {"lang": "vi", "author": "Nguyễn Thị Lan"}


class TestAuthorBox:
    def test_absent_when_keys_absent(self):
        assert blog_render._author_box(FM_BASE) == ("", "")

    def test_vietnamese_pattern(self):
        html, text = blog_render._author_box(
            {**FM_BASE, "author_credential": "Dược sĩ đại học", "reviewed_by": "BS. Trần Văn Minh"})
        assert "Bài viết được tham vấn bởi <strong>BS. Trần Văn Minh</strong>." in html
        assert "<strong>Nguyễn Thị Lan</strong>, Dược sĩ đại học." in html
        assert "Bài viết được tham vấn bởi BS. Trần Văn Minh." in text

    def test_only_present_keys_render(self):
        html, _ = blog_render._author_box({**FM_BASE, "reviewed_by": "BS. A"})
        assert "tham vấn" in html and "Dược sĩ" not in html

    def test_html_escaped(self):
        html, _ = blog_render._author_box(
            {**FM_BASE, "author_credential": "<script>alert(1)</script>", "reviewed_by": '"><img src=x>'})
        assert "<script>" not in html and "<img" not in html and "&lt;script&gt;" in html

    def test_english_fallback(self):
        html, _ = blog_render._author_box({"lang": "en", "author": "Ann", "reviewed_by": "Dr. B"})
        assert "Reviewed by" in html

    def _render(self, tmp_path, extra):
        md = tmp_path / "s.md"
        md.write_text(
            "---\ntitle: Tiêu đề\ndescription: Mô tả\ndate: 2026-09-01\nauthor: Lan\nlang: vi\n"
            f"slug: s\ncanonical: https://example.com/s/\n{extra}---\n\n## Mục\n\nNội dung bài viết.\n",
            encoding="utf-8")
        out = blog_render._render_html(md, tmp_path, "hero.png")
        return out.read_text(encoding="utf-8")

    def test_rendered_html_contains_box_and_jsonld(self, tmp_path):
        html = self._render(tmp_path, "author_credential: Dược sĩ\nreviewed_by: BS. Minh\n")
        assert '<p class="author-box">' in html and "Bài viết được tham vấn bởi" in html
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        assert ld["author"]["jobTitle"] == "Dược sĩ" and ld["reviewedBy"]["name"] == "BS. Minh"

    def test_render_without_keys_has_no_box(self, tmp_path):
        html = self._render(tmp_path, "")
        assert 'class="author-box"' not in html.split("</style>")[1]
        assert "reviewedBy" not in html
