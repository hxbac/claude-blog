"""Phase J items 3 to 5: the draft-mode rubric, ai_structure wiring, Gate 4 bar.

Finding A3: the 100-point score tied real Vietnamese prose with AI slop
(48, 42, 48) because it measured a published site. Draft mode scores only what
a draft controls and lists site-level items as a checklist outside the
denominator.

Samples (the review's own files were not kept; see fixtures):
  vi_real_post_kiem_soat.md      the real post from blog-results/ (verbatim copy)
  vi_human_review_sample.md      RECONSTRUCTED human personal post
  vi_slop_review_sample.md       RECONSTRUCTED AI-slop post
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_blog
import draft_rubric

FIXTURES = Path(__file__).parent / "fixtures"
REAL = FIXTURES / "vi_real_post_kiem_soat.md"
HUMAN = FIXTURES / "vi_human_review_sample.md"
SLOP = FIXTURES / "vi_slop_review_sample.md"


def draft(path: Path) -> dict:
    return analyze_blog.analyze_file(str(path), "draft")


def write_post(tmp_path: Path, body: str, **fm: str) -> Path:
    meta = {
        "title": "Cách đo chi phí vận chuyển thật của một đơn hàng",
        "description": "Ba phép đo giúp bạn biết chi phí vận chuyển thật của từng đơn hàng và khi nào nên đổi đơn vị.",
        "author": "Trần Minh Khoa", "date": "2026-09-01", "slug": "chi-phi-van-chuyen",
        "canonical": "https://shop.vn/chi-phi-van-chuyen", "lang": "vi",
    }
    meta.update(fm)
    head = "\n".join(f'{k}: "{v}"' for k, v in meta.items() if v is not None)
    path = tmp_path / "post.md"
    path.write_text(f"---\n{head}\n---\n\n# {meta['title']}\n\n{body}\n", encoding="utf-8")
    return path


FILLER = (
    "Lấy tổng tiền trả cho đơn vị vận chuyển trong ba mươi ngày rồi chia cho số đơn giao thành công. "
    "Con số này giúp bạn so sánh các đơn vị với nhau một cách công bằng. "
    "Hãy ghi lại từng khoản phụ phí vào một bảng tính riêng để đối chiếu cuối tháng. "
)
BODY = (FILLER * 3).strip()


class TestSampleScores:
    """The acceptance numbers of docs/review/05-roadmap.md Phase J."""

    def test_slop_sample_lands_below_sixty(self):
        assert draft(SLOP)["score"]["total"] < 60

    def test_human_samples_land_above_eighty(self):
        assert draft(HUMAN)["score"]["total"] > 80
        assert draft(REAL)["score"]["total"] > 80

    def test_slop_scores_below_both_human_samples(self):
        slop = draft(SLOP)["score"]["total"]
        assert slop < draft(HUMAN)["score"]["total"]
        assert slop < draft(REAL)["score"]["total"]

    def test_slop_is_blocked_and_humans_pass_gate4(self):
        assert draft(SLOP)["score"]["gate4"]["ready"] is False
        assert draft(HUMAN)["score"]["gate4"]["ready"] is True
        assert draft(REAL)["score"]["gate4"]["ready"] is True

    def test_full_rubric_still_cannot_tell_them_apart(self):
        """Regression record of finding A3: this is why draft mode exists."""
        full = {p.name: analyze_blog.analyze_file(str(p), "full")["score"]["total"]
                for p in (SLOP, HUMAN, REAL)}
        assert max(full.values()) < 60
        assert abs(full[SLOP.name] - full[REAL.name]) < 15


class TestSiteItemsAreOutsideTheDenominator:
    def test_internal_links_do_not_change_the_draft_score(self, tmp_path):
        bare = draft(write_post(tmp_path, BODY))
        linked_body = BODY + " Xem thêm [bài liên quan](/bai-lien-quan), [một bài khác](/bai-khac) và [bài thứ ba](/bai-ba)."
        linked = draft(write_post(tmp_path, linked_body))
        assert bare["score"]["total"] == linked["score"]["total"]

    def test_checklist_lists_the_site_level_items(self):
        keys = {row["item"] for row in draft(REAL)["score"]["prepublish_checklist"]}
        assert {"internal_links", "about_contact", "schema_jsonld", "open_graph",
                "crawler_access", "canonical_live", "images_alt", "legal_disclosure"} <= keys

    def test_no_site_item_is_a_scored_item(self):
        items = set(draft(REAL)["score"]["items"])
        for forbidden in ("internal_links", "about_contact", "schema", "open_graph", "crawler_access"):
            assert forbidden not in items

    def test_placeholder_canonical_is_a_todo(self):
        rows = {r["item"]: r for r in draft(REAL)["score"]["prepublish_checklist"]}
        assert rows["canonical_live"]["status"] == "todo"

    def test_not_applicable_items_are_excluded_not_lost(self):
        score = draft(HUMAN)["score"]
        assert "headings" in score["excluded_from_denominator"]
        assert score["applicable_max"] < 100
        assert score["total"] == round(
            sum(i["score"] for i in score["items"].values() if i["applicable"])
            / score["applicable_max"] * 100)

    def test_english_post_excludes_register(self, tmp_path):
        path = tmp_path / "post.md"
        path.write_text(
            '---\ntitle: "How to measure shipping cost per order"\n'
            'description: "Three measurements that show what one order really costs to ship to a customer."\n'
            'author: "Jane Doe"\ndate: 2026-09-01\nslug: shipping-cost\ncanonical: "https://shop.example/x"\n---\n\n'
            "# How to measure shipping cost per order\n\n" + "Divide the total paid to carriers by delivered orders. " * 12 + "\n",
            encoding="utf-8")
        score = analyze_blog.analyze_file(str(path), "draft")["score"]
        assert "register" in score["excluded_from_denominator"]


class TestModeSelection:
    def test_auto_is_draft_for_markdown_and_full_for_html(self):
        assert analyze_blog._resolve_mode("auto", ".md") == "draft"
        assert analyze_blog._resolve_mode(None, ".mdx") == "draft"
        assert analyze_blog._resolve_mode("auto", ".html") == "full"
        assert analyze_blog._resolve_mode("full", ".md") == "full"
        assert analyze_blog._resolve_mode("draft", ".html") == "draft"

    def test_python_api_default_stays_full_for_existing_callers(self):
        assert analyze_blog.analyze_file(str(REAL))["score"].get("mode") is None

    def test_cli_defaults_to_draft_for_a_markdown_file(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "analyze_blog.py"), str(REAL)],
            capture_output=True, text=True, check=True)
        assert json.loads(proc.stdout)["score"]["mode"] == "draft"

    def test_cli_mode_full_restores_the_published_rubric(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "analyze_blog.py"), str(REAL), "--mode", "full"],
            capture_output=True, text=True, check=True)
        assert "mode" not in json.loads(proc.stdout)["score"]

    def test_markdown_report_is_vietnamese_for_a_vietnamese_post(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "analyze_blog.py"), str(SLOP), "--format", "markdown"],
            capture_output=True, text=True, check=True)
        assert "Chưa đạt Gate 4" in proc.stdout
        assert "Danh sách trước khi đăng" in proc.stdout

    def test_table_and_category_views_work_in_draft_mode(self):
        base = [sys.executable, str(ROOT / "scripts" / "analyze_blog.py"), str(REAL)]
        table = subprocess.run(base + ["--format", "table"], capture_output=True, text=True, check=True)
        assert "draft" in table.stdout and "GATE4" in table.stdout
        cat = subprocess.run(base + ["--category", "voice"], capture_output=True, text=True, check=True)
        assert "Voice and Register" in cat.stdout


class TestAiStructureIsWired:
    def test_analysis_exposes_ai_structure_with_the_frontmatter_language(self):
        result = draft(SLOP)
        assert result["ai_structure"]["lang"] == "vi"
        assert "cluster_score" in result["ai_structure"]

    def test_english_frontmatter_selects_english_lists(self, tmp_path):
        path = tmp_path / "post.md"
        path.write_text("---\ntitle: T\nlang: en\n---\n\n# T\n\nCertainly! Here is the summary.\n", encoding="utf-8")
        result = analyze_blog.analyze_file(str(path), "draft")
        assert result["ai_structure"]["lang"] == "en"

    def test_cli_reads_lang_from_frontmatter(self, tmp_path):
        path = tmp_path / "vi.md"
        path.write_text("---\ntitle: T\nlang: vi\n---\n\n# T\n\nChắc chắn rồi, đây là bài viết.\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ai_structure.py"), str(path), "--format", "json"],
            capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        assert report["lang"] == "vi"
        assert "chatbot_residue" in report["checks_summary"]

    def test_cluster_score_reaches_the_number(self, tmp_path):
        clean = draft(write_post(tmp_path, BODY))["score"]["items"]["structure_cluster"]["score"]
        assert clean == 12
        loud = BODY + (
            "\n\n## Kết luận\n\nTóm lại.\n\nĐó chính là mấu chốt.\n\n"
            "Điện, nước và không gian. Bàn, ghế và tủ. Xe, nhà và đất. Mưa, gió và bão.\n")
        dirty = draft(write_post(tmp_path, loud))
        assert dirty["ai_structure"]["cluster_score"] >= 1
        assert dirty["score"]["items"]["structure_cluster"]["score"] < clean


class TestP0Definition:
    def codes(self, result: dict) -> set:
        return {p["code"] for p in result["score"]["p0"]}

    def test_register_drift_above_the_ratio_is_p0(self):
        assert "register_drift" in self.codes(draft(SLOP))

    def test_register_drift_below_the_ratio_is_not(self, tmp_path):
        body = BODY + " Bạn nên đo lại. Bạn nên thử. Bạn nên xem. Bạn nên hỏi. Quý khách hãy đợi. Quý vị nên đọc."
        assert "register_drift" not in self.codes(draft(write_post(tmp_path, body)))

    def test_chatbot_residue_is_p0(self, tmp_path):
        body = BODY + "\n\nChắc chắn rồi, mình sẽ viết tiếp phần còn lại."
        assert "chatbot_residue" in self.codes(draft(write_post(tmp_path, body)))

    def test_attributed_statistic_without_a_source_is_p0(self, tmp_path):
        body = BODY + "\n\nTheo một nghiên cứu gần đây, 87% khách hàng bỏ giỏ hàng vì phí ship."
        result = draft(write_post(tmp_path, body))
        assert "fabricated_statistic" in self.codes(result)
        assert result["score"]["gate4"]["ready"] is False

    def test_attributed_statistic_with_a_link_is_fine(self, tmp_path):
        body = BODY + "\n\nTheo [báo cáo của Cục TMĐT](https://www.moit.gov.vn/bao-cao), 87% khách bỏ giỏ hàng vì phí ship."
        assert "fabricated_statistic" not in self.codes(draft(write_post(tmp_path, body)))

    def test_illustrative_number_is_fine(self, tmp_path):
        body = BODY + "\n\nVí dụ, đơn vị B rẻ hơn 2 nghìn nhưng tỷ lệ hoàn cao hơn 3 phần trăm."
        result = draft(write_post(tmp_path, body))
        assert not self.codes(result)
        assert result["score"]["items"]["evidence"]["score"] == 14

    def test_unattributed_unsourced_number_costs_points_but_is_not_p0(self, tmp_path):
        body = BODY + "\n\nChi phí thật thường cao hơn bảng giá 25 phần trăm."
        result = draft(write_post(tmp_path, body))
        assert "fabricated_statistic" not in self.codes(result)
        assert result["score"]["items"]["evidence"]["score"] == 10

    def test_own_measurement_is_credited(self, tmp_path):
        body = BODY + "\n\nMình đo 40 đơn tháng trước và thấy 30 phần trăm bị hoàn."
        assert draft(write_post(tmp_path, body))["score"]["items"]["evidence"]["score"] == 14

    def test_legal_disclosure_hook_feeds_p0(self, monkeypatch, tmp_path):
        path = write_post(tmp_path, BODY)
        doc = draft_rubric.legal_disclosure_p0.__doc__
        assert draft(path)["score"]["p0"] == []      # no keys set: never a P0
        monkeypatch.setattr(
            draft_rubric, "legal_disclosure_p0",
            lambda fm, body, lang: [{"code": "legal_disclosure", "message": "Thiếu khai báo quảng cáo."}])
        result = draft(path)
        assert self.codes(result) == {"legal_disclosure"}
        assert result["score"]["gate4"]["ready"] is False
        assert "vi_compliance" in doc and "STUB" not in doc

    def test_p0_forces_gate4_closed_even_at_a_high_number(self, monkeypatch, tmp_path):
        path = write_post(tmp_path, BODY)
        monkeypatch.setattr(draft_rubric, "legal_disclosure_p0",
                            lambda fm, body, lang: [{"code": "legal_disclosure", "message": "x"}])
        score = draft(path)["score"]
        assert score["total"] >= 85 and score["gate4"]["ready"] is False


class TestRubricItems:
    def test_title_case_vietnamese_title_is_flagged(self, tmp_path):
        result = draft(write_post(tmp_path, BODY, title="Cách Chọn Máy Pha Cà Phê Cho Quán Nhỏ"))
        assert any("viết hoa từng chữ" in i["issue"] for i in result["score"]["issues"])

    def test_sentence_case_title_is_not(self, tmp_path):
        assert not any("viết hoa" in i["issue"] for i in draft(write_post(tmp_path, BODY))["score"]["issues"])

    def test_is_title_case_ignores_short_or_acronym_titles(self):
        assert draft_rubric.is_title_case("Cách Chọn Máy Pha Cà Phê Cho Quán") is True
        assert draft_rubric.is_title_case("Chọn máy pha cà phê cho quán nhỏ") is False
        assert draft_rubric.is_title_case("Cách đo SEO") is False

    def test_trust_boilerplate_in_body_is_flagged(self, tmp_path):
        body = BODY + "\n\nBài viết được biên tập và kiểm chứng bởi đội ngũ chuyên gia. Liên hệ chúng tôi để biết thêm."
        result = draft(write_post(tmp_path, body))
        assert result["score"]["items"]["no_trust_boilerplate"]["score"] == 0
        assert any("chân trang" in i["issue"] for i in result["score"]["issues"])

    def test_meta_description_length_is_checked(self, tmp_path):
        result = draft(write_post(tmp_path, BODY, description="Quá ngắn."))
        assert result["score"]["items"]["snippet_length"]["score"] < 6

    def test_missing_lang_on_a_vietnamese_post_is_called_out(self, tmp_path):
        result = draft(write_post(tmp_path, BODY, lang=None))
        assert result["language"] == "vi"   # detected anyway
        assert any("lang: vi" in i["issue"] for i in result["score"]["issues"])

    def test_generic_author_is_flagged(self, tmp_path):
        result = draft(write_post(tmp_path, BODY, author="Nhóm nội dung"))
        assert any("tên người thật" in i["issue"] for i in result["score"]["issues"])

    def test_long_sentences_lower_the_distribution_item(self, tmp_path):
        long_sentence = ("Khi bạn tính chi phí vận chuyển cho từng đơn hàng trong suốt ba mươi ngày gần nhất "
                         "thì bạn cần cộng cả phí thu hộ, phí hoàn, phí đóng gói và cả thời gian nhân viên "
                         "gọi lại cho khách hàng để xác nhận địa chỉ giao hàng. ")
        heavy = draft(write_post(tmp_path, long_sentence * 6))
        light = draft(write_post(tmp_path, BODY))
        assert heavy["score"]["items"]["sentence_length"]["score"] < light["score"]["items"]["sentence_length"]["score"]

    def test_stub_cannot_pass(self, tmp_path):
        result = draft(write_post(tmp_path, "Bài này ngắn."))
        assert result["score"]["capped"].startswith("stub:")
        assert result["score"]["total"] <= draft_rubric.STUB_SCORE_CAP
        assert result["score"]["gate4"]["ready"] is False

    def test_lexical_density_uses_the_profile_scanner(self):
        tells = draft(SLOP)["lexical_tells"]
        assert tells["model"] == "vi_profile.scan_tells"
        assert tells["density_per_1000"] > 20

    def test_issues_are_vietnamese_for_a_vietnamese_post(self):
        issues = " ".join(i["issue"] for i in draft(SLOP)["score"]["issues"])
        assert "Xưng hô không nhất quán" in issues and "Xóa câu này" in issues

    def test_gate4_threshold_constant_is_85(self):
        assert draft_rubric.GATE4_MIN_SCORE == 85
        assert draft(SLOP)["score"]["gate4"]["min_score"] == 85

    def test_vietnamese_examples_are_counted(self):
        eng = analyze_blog.analyze_engagement("Ví dụ, một đơn hàng. Chẳng hạn như thế này.", "vi")
        assert eng["example_count"] >= 2
        assert analyze_blog.analyze_engagement("Ví dụ, một đơn hàng.", "en")["example_count"] == 0
