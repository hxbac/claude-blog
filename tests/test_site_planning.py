"""Tests for the planning commands of scripts/site_inventory.py (gaps, stale,
overlap). Inventories are built in memory or in tmp_path; no network."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import site_inventory as si  # noqa: E402
import vi_keywords  # noqa: E402


def row(url, type_, title, **kw):
    r = si.blank_row()
    r.update({"url": url, "type": type_, "title": title})
    r.update(kw)
    return r


def inventory():
    return [
        row("https://s.vn/blog/cach-chon-ban-phim-co", "post", "Cách chọn bàn phím cơ cho dân văn phòng",
            lastmod="2025-01-10T08:00:00+07:00"),
        row("https://s.vn/blog/may-xay-sinh-to", "post", "Máy xay sinh tố loại nào bền",
            lastmod="2026-06-01"),
        row("https://s.vn/blog/khong-ngay", "post", "Bài chưa rõ ngày"),
        row("https://s.vn/blog/ngay-hong", "post", "Bài ngày hỏng", lastmod="khong biet"),
        row("https://s.vn/blog/cu-nhat", "post", "Bài cũ nhất", lastmod="2023-03-03"),
        row("https://s.vn/c/ban-phim-co", "category", "Bàn Phím Cơ / Cửa hàng S"),
        row("https://s.vn/c/may-xay", "category", "Máy Xay Sinh Tố"),
        row("https://s.vn/c/chuot-gaming", "category", "Chuột Gaming"),
        row("https://s.vn/c/tai-nghe-bluetooth", "category", "Tai Nghe Bluetooth", exclude="yes"),
        row("https://s.vn/c/loa-cu", "gone", "Loa Kéo Cũ"),
        row("https://s.vn/p/webcam-4k", "product", "Webcam Họp Trực Tuyến 4K Pro", priority="5",
            category="Webcam"),
        row("https://s.vn/p/day-cap", "product", "Dây Cáp Sạc Nhanh Type C", priority="2"),
        row("https://s.vn/p/chuot-g102", "product", "Chuột Gaming G102 Đen", category="Chuột Gaming"),
        row("https://s.vn/p/loa-gone", "gone", "Loa Mini Ẩn", priority="5"),
    ]


# ------------------------------------------------------------------- gaps

def test_gaps_lists_only_uncovered_rows_from_inventory():
    res = si.find_gaps(inventory(), top=20)
    names = {g["name"] for g in res["gaps"]}
    assert "Chuột Gaming" in names
    assert "Webcam Họp Trực Tuyến 4K Pro" in names
    # covered by a post, so not a gap
    assert "Bàn Phím Cơ" not in names
    assert "Máy Xay Sinh Tố" not in names
    # never invented: every gap is a real inventory URL
    urls = {r["url"] for r in inventory()}
    assert all(g["url"] in urls for g in res["gaps"])


def test_gaps_excludes_gone_excluded_and_low_priority_products():
    res = si.find_gaps(inventory(), top=50)
    names = " ".join(g["name"] for g in res["gaps"])
    assert "Tai Nghe" not in names      # exclude=yes
    assert "Loa" not in names           # type=gone (category and product)
    assert "Dây Cáp" not in names       # priority 2 < 4
    assert "G102" not in names          # no priority set (default 3)


def test_gaps_name_drops_seo_tail():
    res = si.find_gaps([row("https://s.vn/c/x", "category", "Ghế Công Thái Học / Cửa hàng S | S.vn")], top=5)
    assert res["gaps"][0]["name"] == "Ghế Công Thái Học"


def test_gaps_threshold_is_documented_and_applied():
    assert 0 < si.COVERAGE_THRESHOLD < 1
    assert "Ngưỡng: " in si.render_gaps(
        si.suggest_topics(si.find_gaps([row("https://s.vn/c/a", "category", "Áo")])))
    rows = [row("https://s.vn/b/ban-phim", "post", "Bàn phím cơ nào tốt"),
            row("https://s.vn/c/ban-phim-co-mini", "category", "Bàn Phím Cơ Mini")]
    c = si.find_gaps(rows, threshold=1.01)["gaps"][0]["best_coverage"]
    assert 0 < c < 1
    assert si.find_gaps(rows, threshold=c - 0.02)["total_gaps"] == 0   # covered
    assert si.find_gaps(rows, threshold=c + 0.02)["total_gaps"] == 1   # gap


def test_gaps_diacritic_insensitive_coverage():
    rows = [row("https://s.vn/b/1", "post", "ban phim co tot nhat"),
            row("https://s.vn/c/1", "category", "Bàn Phím Cơ")]
    assert si.find_gaps(rows)["total_gaps"] == 0


def test_gaps_no_posts_means_everything_is_a_gap_and_order_is_priority_first():
    rows = [row("https://s.vn/c/a", "category", "Áo Thun"),
            row("https://s.vn/p/b", "product", "Giày Chạy Bộ Pro", priority="5")]
    res = si.find_gaps(rows)
    assert res["total_gaps"] == 2
    assert res["gaps"][0]["name"] == "Giày Chạy Bộ Pro"


def test_gaps_category_with_more_products_ranks_higher():
    rows = [row("https://s.vn/c/a", "category", "Áo Thun"),
            row("https://s.vn/c/b", "category", "Quần Tây"),
            row("https://s.vn/p/1", "product", "x1", category="Quần Tây"),
            row("https://s.vn/p/2", "product", "x2", category="Quần Tây")]
    res = si.find_gaps(rows)
    assert [g["name"] for g in res["gaps"]] == ["Quần Tây", "Áo Thun"]
    assert res["gaps"][0]["products_in_category"] == 2


def test_suggest_topics_uses_build_variants_and_real_names_without_volumes(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("volumes must not be fetched without --volumes")
    monkeypatch.setattr(vi_keywords, "fetch_volumes", boom)
    res = si.suggest_topics(si.find_gaps(inventory(), top=5))
    g = next(x for x in res["gaps"] if x["name"] == "Chuột Gaming")
    assert g["variants"][0] == "chuột gaming"
    assert "chuot gaming" in g["variants"]
    assert "Chuột Gaming" in g["topic"]
    out = si.render_gaps(res)
    assert out.startswith("Gợi ý chủ đề") and "| Danh mục |" in out
    assert "tiêu đề" in out  # says the post body is unknown


def test_suggest_topics_volumes(monkeypatch):
    monkeypatch.setattr(vi_keywords, "fetch_volumes",
                        lambda kws, limit: ({"chuột gaming": 1900}, ""))
    res = si.suggest_topics(si.find_gaps(inventory(), top=5), volumes=True)
    g = next(x for x in res["gaps"] if x["name"] == "Chuột Gaming")
    assert g["volumes"]["chuột gaming"] == 1900
    assert "chuột gaming (1900)" in si.render_gaps(res)


def test_suggest_topics_volumes_without_key_says_so(monkeypatch):
    monkeypatch.setattr(vi_keywords, "has_dataforseo_key", lambda: False)
    res = si.suggest_topics(si.find_gaps(inventory(), top=5), volumes=True)
    assert "DataForSEO" in res["volumes_note"]


def test_cmd_gaps_json(tmp_path, monkeypatch, capsys):
    site = tmp_path / "sites" / "s.vn"
    site.mkdir(parents=True)
    (site / "site.toml").write_text('base_url = "https://s.vn"\ncms = "other"\n', encoding="utf-8")
    si.write_csv_rows(site / "inventory.csv", inventory())
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "sites"))
    assert si.main(["gaps", "--json", "--top", "1"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["gaps"]) == 1 and data["total_gaps"] == 2 and data["gaps"][0]["variants"]


# ------------------------------------------------------------------ stale

def test_stale_orders_oldest_first_and_lists_missing_lastmod_after():
    res = si.find_stale(inventory(), Path("/nonexistent"), today=date(2026, 10, 2), top=10)
    assert [p["url"].rsplit("/", 1)[-1] for p in res["posts"]] == [
        "cu-nhat", "cach-chon-ban-phim-co", "may-xay-sinh-to"]
    assert res["posts"][0]["age_days"] == (date(2026, 10, 2) - date(2023, 3, 3)).days
    missing = {p["url"].rsplit("/", 1)[-1] for p in res["no_lastmod"]}
    assert missing == {"khong-ngay", "ngay-hong"}
    text = si.render_stale(res)
    assert text.index("cu-nhat") < text.index("may-xay-sinh-to") < text.index("khong-ngay")
    assert "không rõ ngày" in text


def test_stale_top_limits_dated_first():
    res = si.find_stale(inventory(), Path("/nonexistent"), today=date(2026, 10, 2), top=2)
    assert len(res["posts"]) == 2 and res["no_lastmod"] == [] and res["no_lastmod_total"] == 2


def test_stale_skips_gone_and_excluded_posts():
    rows = [row("https://s.vn/a", "post", "A", lastmod="2020-01-01", exclude="yes"),
            row("https://s.vn/b", "gone", "B", lastmod="2019-01-01")]
    res = si.find_stale(rows, Path("/nonexistent"))
    assert res["posts"] == [] and res["no_lastmod_total"] == 0


def test_stale_finds_gone_urls_linked_from_drafts(tmp_path):
    d = tmp_path / "blog-results" / "bai-1"
    d.mkdir(parents=True)
    (d / "bai-1.md").write_text(
        "---\ntitle: x\n---\n\nXem [loa](https://s.vn/c/loa-cu/?utm_source=a) và [chuột](https://s.vn/c/chuot-gaming).\n"
        "Cũng <a href=\"/p/loa-gone\">loa mini</a>.\n", encoding="utf-8")
    (d / "review.md").write_text("[loa](https://s.vn/c/loa-cu)", encoding="utf-8")
    res = si.find_stale(inventory(), tmp_path / "blog-results", "https://s.vn", today=date(2026, 10, 2))
    got = sorted(g["url"] for g in res["gone_linked"])
    assert got == ["https://s.vn/c/loa-cu", "https://s.vn/p/loa-gone"]
    assert all(g["draft"].endswith("bai-1.md") for g in res["gone_linked"])
    assert "https://s.vn/c/loa-cu" in si.render_stale(res)


def test_stale_default_drafts_dir_is_next_to_sites_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "workspace" / "sites"))
    assert si.drafts_dir_for(None) == tmp_path / "workspace" / "blog-results"
    assert si.drafts_dir_for(str(tmp_path / "x")) == tmp_path / "x"


def test_cmd_stale_json_with_drafts_override(tmp_path, monkeypatch, capsys):
    site = tmp_path / "sites" / "s.vn"
    site.mkdir(parents=True)
    (site / "site.toml").write_text('base_url = "https://s.vn"\ncms = "other"\n', encoding="utf-8")
    si.write_csv_rows(site / "inventory.csv", inventory())
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "sites"))
    assert si.main(["stale", "--json", "--drafts", str(tmp_path / "none")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["posts"][0]["url"].endswith("cu-nhat") and data["gone_linked"] == []


# ---------------------------------------------------------------- overlap

def test_overlap_flags_post_vs_draft_and_exact_focus_keyword(tmp_path):
    rows = [row("https://s.vn/a", "post", "Cách chọn máy pha cà phê cho quán nhỏ", focus_keyword="máy pha cà phê"),
            row("https://s.vn/b", "post", "Học đàn guitar cho người mới bắt đầu"),
            row("https://s.vn/c", "post", "Top máy pha cà phê tốt nhất", focus_keyword="Máy pha cà phê")]
    d = tmp_path / "br" / "p"
    d.mkdir(parents=True)
    (d / "p.md").write_text("---\ntitle: Cách chọn máy pha cà phê cho quán nhỏ\nslug: p\n---\n# H\n", encoding="utf-8")
    res = si.find_overlaps(rows, tmp_path / "br")
    pairs = {(p["a"], p["b"]): p for p in res["pairs"]}
    assert ("https://s.vn/a", "https://s.vn/c") in pairs
    assert pairs[("https://s.vn/a", "https://s.vn/c")]["severity"] == "Nghiêm trọng"
    assert any(p["a_origin"] == "bản nháp" or p["b_origin"] == "bản nháp" for p in res["pairs"])
    assert not any("s.vn/b" in (p["a"], p["b"]) for p in res["pairs"])
    assert "cạnh tranh" in si.render_overlaps(res)


def test_overlap_none():
    rows = [row("https://s.vn/a", "post", "Học đàn guitar"), row("https://s.vn/b", "post", "Nấu phở bò")]
    assert si.find_overlaps(rows, Path("/nonexistent"))["pairs"] == []


def test_gaps_folds_subcategories_under_parent():
    targets = [
        {"type": "category", "name": "Balo", "products_in_category": 2},
        {"type": "category", "name": "Balo Camping", "products_in_category": 3},
        {"type": "category", "name": "Balo Camping Pro", "products_in_category": 1},
        {"type": "category", "name": "Ví", "products_in_category": 0},
        {"type": "product", "name": "Balo Smart X", "products_in_category": 0},
    ]
    out = si.fold_subcategories(targets)
    names = [t["name"] for t in out]
    assert names == ["Balo", "Ví", "Balo Smart X"]
    assert out[0]["subcategories"] == ["Balo Camping", "Balo Camping Pro"]
    assert out[0]["products_in_category"] == 6


def test_noun_variant_uses_cach_chon():
    assert si._noun_variants(["balo", "cách balo", "giá balo"], "balo") == ["balo", "cách chọn balo", "giá balo"]


def test_bag_names_get_no_bich_variant_and_no_brackets():
    rows = [{"type": "category", "name": "Dây Nịt Nam (Thắt Lưng)", "url": "https://x.vn/c/day-nit",
             "priority": 3, "products_in_category": 0, "best_coverage": 0.0, "closest_post": ""},
            {"type": "category", "name": "Túi Đeo Chéo", "url": "https://x.vn/c/tui",
             "priority": 3, "products_in_category": 0, "best_coverage": 0.0, "closest_post": ""}]
    out = si.suggest_topics({"posts_considered": 0, "threshold": 0.5, "total_gaps": 2, "gaps": rows})
    belt, bag = out["gaps"]
    assert belt["variants"][0] == "dây nịt nam"
    assert not any("bịch" in v for v in bag["variants"])
