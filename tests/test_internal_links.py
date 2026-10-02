"""Phase Q: internal_links.py, Gate 5 site check, draft rubric, publish hook.

No network. The site is the committed fixture under
``tests/fixtures/internal_links/sites/cuahang.test``; a test copies it into
``tmp_path`` and points ``CLAUDE_BLOG_SITES_ROOT`` there.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import analyze_blog  # noqa: E402
import blog_preflight  # noqa: E402
import draft_rubric  # noqa: E402
import internal_links as il  # noqa: E402
import publish_cms  # noqa: E402
import site_inventory as si  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "internal_links" / "sites"
BASE = "https://cuahang.test"
VI_DA_NAM = BASE + "/collections/vi-da-nam"
PROD_DEN = BASE + "/products/vi-ngan-bi-mat-da-bo-mau-den"
PROD_NAU = BASE + "/products/vi-ngan-bi-mat-da-bo-mau-nau"
DAY_NIT = BASE + "/collections/day-nit"
BAO_QUAN = BASE + "/blogs/cach-bao-quan-do-da"
PHOI_MAU = BASE + "/blogs/phoi-mau-trang-phuc"
DOI_TRA = BASE + "/pages/chinh-sach-doi-tra"
GONE = BASE + "/blogs/bai-da-go"
EXCLUDED = BASE + "/blogs/bai-loai-tru"


@pytest.fixture
def root(tmp_path, monkeypatch):
    dest = tmp_path / "sites"
    shutil.copytree(FIX, dest)
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(dest))
    return dest


@pytest.fixture
def site(root):
    return il.load_site(root / "cuahang.test")


FM = """---
title: Cách chọn ví da nam bền và gọn
description: Hướng dẫn chọn ví da nam.
slug: cach-chon-ma-moi
canonical: https://cuahang.test/blogs/cach-chon-ma-moi
lang: vi
date: 2026-10-02
author: Nguyễn Minh Anh
%s---
"""

BODY = """
# Cách chọn ví da nam bền và gọn

Một chiếc ví tốt đi cùng bạn nhiều năm, nên chọn kỹ ngay từ đầu.

## Chất liệu

Khi cầm thử, hãy xem kỹ vi da nam bằng da bò vì mép da và đường chỉ quyết định độ bền.

Người hay để ví trong túi sau nên cân nhắc một chiếc ví ngăn bí mật da bò cho tờ tiền dự phòng.

Đồ da cần được bảo quản đồ da đúng cách để không nứt mép.

## Phối đồ

Hãy chọn ví cùng tông với dây nịt nam và giày, theo hướng dẫn phối màu trang phục của mình.
"""


def draft_dir(tmp_path, body=BODY, extra="", name="cach-chon-ma-moi"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / f"{name}.md").write_text((FM % extra) + body, encoding="utf-8")
    return d


def md_of(d):
    return (d / "cach-chon-ma-moi.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Draft structure
# ---------------------------------------------------------------------------

def test_blocks_classify_and_skip_frontmatter():
    text = (FM % "") + """
# Tiêu đề

Đoạn văn một.

```
ví da nam trong mã
```

> Trích dẫn về ví da nam

| a | b |
| - | - |
| ví da nam | x |

- mục một
- mục hai

**Ví da bò có cần sáp không?**

Trả lời về ví da.
"""
    fm, off = il.parse_frontmatter(text)
    assert fm["slug"] == "cach-chon-ma-moi" and fm["lang"] == "vi"
    kinds = [b.kind for b in il.parse_blocks(text, off)]
    assert kinds == ["heading", "paragraph", "code", "quote", "table", "list", "faq", "paragraph"]


def test_spans_never_cover_links_images_code_or_urls():
    text = "Xem [ví da nam](https://x.vn/a) và ![ví da nam](a.png) hay `ví da` rồi https://x.vn/ví-da-nam nữa."
    covered = {s.text for s in il.iter_spans(text)}
    assert not any("ví da" in c.lower() and c.lower().startswith("ví da") for c in covered
                   if c.lower() in ("ví da nam", "ví da"))
    # every span is clear of the masked ranges
    masks = il._masked(text)
    for s in il.iter_spans(text):
        assert not il._overlaps(s.start, s.end, masks)


def test_find_occurrences_is_diacritic_and_case_insensitive():
    text = "Ví Da Nam rất bền; vi da nam khác. Vì da"
    occ = il.find_occurrences(text, "ví da nam")
    assert [text[a:b] for a, b in occ] == ["Ví Da Nam", "vi da nam"]


def test_density_band_and_exact_allowance():
    assert il.density_band(500)[:2] == (3, 5)
    assert il.density_band(1500)[:2] == (5, 7)
    assert il.density_band(2500)[:2] == (7, 10)
    assert il.density_band(3500)[:2] == (8, 12)
    assert il.max_exact(6) == 1 and il.max_exact(10) == 1 and il.max_exact(25) == 2


def test_buying_guide_detection():
    assert il.is_buying_guide({"content_type": "buying-guide"})
    assert il.is_buying_guide({"type": "comparison"})
    assert il.is_buying_guide({"title": "Cách chọn ví da nam"})
    assert il.is_buying_guide({"title": "Top 10 ví da tốt nhất"})
    assert not il.is_buying_guide({"title": "Cách giặt áo thun", "type": "how-to-guide"})


# ---------------------------------------------------------------------------
# candidates and duplicates
# ---------------------------------------------------------------------------

def test_candidates_mix_types_and_skip_gone_excluded_and_out_of_stock(site):
    res = il.candidates(site, "ví da bò nam", top=25)
    urls = [c["url"] for c in res["candidates"]]
    assert VI_DA_NAM in urls and PROD_DEN in urls
    assert GONE not in urls and EXCLUDED not in urls
    assert BASE + "/products/vi-card-mong" not in urls        # in_stock = no
    types = {c["type"] for c in res["candidates"]}
    assert {"category", "product"} <= types
    # the two colours are one product
    prods = [c for c in res["candidates"] if c["type"] == "product" and "ngan-bi-mat" in c["url"]]
    assert len(prods) == 1 and prods[0]["variants"] == 2


def test_candidates_flag_duplicate_topic(site):
    res = il.candidates(site, "Cách chọn ví da nam cho người mới bắt đầu")
    assert res["duplicates"], res
    top = res["duplicates"][0]
    assert top["url"] == BASE + "/blogs/cach-chon-vi-da-nam-cu"
    assert top["similarity"] >= il.DUP_THRESHOLD
    assert "blog-rewrite" in il.render_candidates(res)


def test_dup_score_favours_topic_coverage_over_title_tail():
    topic = {"coolify", "cai", "dat"}
    long_tail = {"coolify", "cai", "dat", "nen", "tang", "self", "hosted", "paas"}
    assert il.dup_score(topic, long_tail) >= il.DUP_THRESHOLD          # SEO tail does not hide it
    assert il.dup_score(topic, topic) == 1.0
    assert il.dup_score({"may", "xay", "sinh", "to"}, {"ve", "sinh", "may", "pha", "ca", "phe", "nha"}) < 0.5
    assert il.dup_score({"a"}, {"b"}) == 0.0


def test_unrelated_topic_has_no_duplicates(site):
    assert il.candidates(site, "so sánh điện thoại gập 2026")["duplicates"] == []
    # a post about another product is not a duplicate of the wallet topic
    assert il.find_duplicates(site, "cách chọn ví da nam") == [
        d for d in il.find_duplicates(site, "cách chọn ví da nam")
        if d["url"] == BASE + "/blogs/cach-chon-vi-da-nam-cu"]


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------

def test_suggest_anchor_exists_verbatim_and_keeps_original_spelling(tmp_path, site):
    d = il.load_draft(draft_dir(tmp_path) / "cach-chon-ma-moi.md")
    plan = il.suggest(d, site, target=6)
    assert plan["links"], plan
    for link in plan["links"]:
        block = d.blocks[link["paragraph"]]
        assert link["anchor"] in block.text                    # original spelling, verbatim
        assert block.kind in ("paragraph", "list")
    # written without diacritics in the draft ("vi da nam"), still matched, spelling kept
    body = "\nKhi cầm thử, hãy xem kỹ Vi Da Nam bằng da bò vì mép da quyết định độ bền.\n"
    d2 = il.load_draft(draft_dir(tmp_path, body=body, name="y") / "y.md")
    (link,) = il.suggest(d2, site, target=3)["links"]
    assert link["anchor"] == "Vi Da Nam" and link["url"] == VI_DA_NAM and link["anchor_type"] == "exact"


def test_suggest_never_links_headings_code_quote_or_existing_links(tmp_path, site):
    body = """
# Ví da nam bằng da bò

```
ví da nam bằng da bò
```

> ví da nam bằng da bò

Xem [ví da nam bằng da bò](https://cuahang.test/collections/vi-da-nam) trước.

Dây nịt nam cũng quan trọng không kém ví da nam bằng da bò.
"""
    d = il.load_draft(draft_dir(tmp_path, body=body) / "cach-chon-ma-moi.md")
    plan = il.suggest(d, site, target=6)
    for link in plan["links"]:
        assert d.blocks[link["paragraph"]].kind == "paragraph"
        assert link["paragraph"] != 4 or link["url"] != VI_DA_NAM      # already linked URL
    assert VI_DA_NAM not in [l["url"] for l in plan["links"]]          # one link per URL


def test_suggest_policy_one_per_url_one_per_paragraph_no_self_no_gone_exclude(tmp_path, site):
    d = il.load_draft(draft_dir(tmp_path) / "cach-chon-ma-moi.md")
    plan = il.suggest(d, site, target=8)
    urls = [l["url"] for l in plan["links"]]
    paras = [l["paragraph"] for l in plan["links"]]
    assert len(urls) == len(set(urls)) and len(paras) == len(set(paras))
    assert not {GONE, EXCLUDED, d.canonical} & set(urls)
    # the two colours of one product never both appear
    assert not ({PROD_DEN, PROD_NAU} <= set(urls))


def test_product_share_capped_unless_buying_guide(tmp_path, site):
    body = """
Hãy xem ví ngăn bí mật da bò trong kho.

Một lựa chọn khác là dây nịt da bò khóa tự động cho bộ đồ công sở.

Còn đây là đoạn nói về ví da nam bằng da bò thật cho người mới.
"""
    plain = il.load_draft(draft_dir(tmp_path, body=body, name="a").parent / "a" / "a.md")
    plan = il.suggest(plain, site, target=3)
    products = [l for l in plan["links"] if l["type"] == "product"]
    assert len(products) <= int(0.4 * 3)
    guide = il.load_draft(draft_dir(tmp_path, body=body, extra="content_type: buying-guide\n", name="b") / "b.md")
    assert guide.buying_guide
    plan_g = il.suggest(guide, site, target=3)
    assert sum(l["type"] == "product" for l in plan_g["links"]) >= len(products)


def test_no_product_link_in_first_sentence_of_intro(tmp_path, site):
    body = """
Chiếc ví ngăn bí mật da bò rất tiện. Đoạn mở bài còn một câu nữa.

Ví da nam bằng da bò bền hơn ví giả da.
"""
    d = il.load_draft(draft_dir(tmp_path, body=body, extra="content_type: buying-guide\n") / "cach-chon-ma-moi.md")
    plan = il.suggest(d, site, target=4)
    for link in plan["links"]:
        if link["type"] == "product" and link["paragraph"] == d.intro_block:
            b = d.blocks[link["paragraph"]]
            assert b.text.index(link["anchor"]) >= il.first_sentence_end(b.text)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_inserts_with_original_spelling_and_is_exactly_once(tmp_path, site):
    d = draft_dir(tmp_path)
    path = d / "cach-chon-ma-moi.md"
    res = il.apply_plan(path, site, [{"anchor": "vi da nam", "url": VI_DA_NAM}])
    assert [a["anchor"] for a in res["applied"]] == ["vi da nam"]
    assert f"[vi da nam]({VI_DA_NAM})" in md_of(d)
    assert md_of(d).count(VI_DA_NAM) == 1


def test_apply_refuses_ambiguous_missing_heading_and_linked_anchor(tmp_path, site):
    body = """
## Ví da nam bằng da bò

Ví da nam và ví da nam khác nhau, vì ví da nam có nhiều loại.

Xem [dây nịt nam](https://cuahang.test/collections/day-nit) nữa.

Đoạn khác nhắc dây nịt nam một lần.
"""
    d = draft_dir(tmp_path, body=body)
    path = d / "cach-chon-ma-moi.md"
    before = md_of(d)
    res = il.apply_plan(path, site, [
        {"anchor": "ví da nam", "url": VI_DA_NAM},                      # three times in one paragraph
        {"anchor": "ví da nam", "url": VI_DA_NAM, "paragraph": 0},       # heading
        {"anchor": "không có trong bài", "url": VI_DA_NAM},
        {"anchor": "dây nịt nam", "url": DAY_NIT, "paragraph": 2},       # already linked
    ])
    assert res["applied"] == []
    reasons = " | ".join(r["reason"] for r in res["refused"])
    assert "3 lần" in reasons and "tiêu đề" in reasons
    assert "không có trong bài" in reasons and "liên kết" in reasons
    assert md_of(d) == before


def test_apply_refuses_url_outside_inventory_self_gone_excluded(tmp_path, site):
    d = draft_dir(tmp_path)
    path = d / "cach-chon-ma-moi.md"
    res = il.apply_plan(path, site, [
        {"anchor": "vi da nam", "url": BASE + "/trang-khong-co"},
        {"anchor": "vi da nam", "url": GONE},
        {"anchor": "vi da nam", "url": EXCLUDED},
    ])
    assert res["applied"] == []
    text = " ".join(r["reason"] for r in res["refused"])
    assert "site_inventory.py add" in text and "type=gone" in text and "exclude" in text


def test_apply_one_link_per_paragraph_and_per_url(tmp_path, site):
    body = "\nDây nịt nam đi cùng ví da nam trong cùng một đoạn.\n\nVí da nam là chủ đề chính của đoạn này.\n"
    d = draft_dir(tmp_path, body=body)
    path = d / "cach-chon-ma-moi.md"
    res = il.apply_plan(path, site, [
        {"anchor": "dây nịt", "url": DAY_NIT, "paragraph": 0},
        {"anchor": "ví da", "url": VI_DA_NAM, "paragraph": 0},           # same paragraph
        {"anchor": "ví da", "url": DAY_NIT, "paragraph": 1},             # same URL again
        {"anchor": "ví da", "url": VI_DA_NAM, "paragraph": 1},
    ])
    assert [a["url"] for a in res["applied"]] == [DAY_NIT, VI_DA_NAM]
    reasons = [r["reason"] for r in res["refused"]]
    assert any("oạn này đã có" in r for r in reasons) and any("mỗi URL một lần" in r for r in reasons)


def test_apply_blocks_self_link(tmp_path, site):
    d = draft_dir(tmp_path, body="\nĐọc thêm ví da nam ở đây.\n")
    path = d / "cach-chon-ma-moi.md"
    (root := site.dir.parent)  # noqa: F841
    rows = si.load_inventory(site.dir)
    rows.append({**si.blank_row(), "url": "https://cuahang.test/blogs/cach-chon-ma-moi",
                 "type": "post", "title": "Cách chọn ví da nam bền và gọn"})
    si.write_csv_rows(site.dir / "inventory.csv", rows)
    res = il.apply_plan(path, il.load_site(site.dir), [
        {"anchor": "ví da nam", "url": "https://cuahang.test/blogs/cach-chon-ma-moi"}])
    assert res["applied"] == [] and "chính nó" in res["refused"][0]["reason"]


def test_apply_resolves_placeholder_and_reports_leftovers(tmp_path, site):
    body = """
Hãy đọc [INTERNAL-LINK: dây nịt nam → danh mục dây nịt] trước khi chọn.

Còn đây [INTERNAL-LINK: máy xay sinh tố → không có trên web] chưa có trang.
"""
    d = draft_dir(tmp_path, body=body)
    path = d / "cach-chon-ma-moi.md"
    res = il.apply_plan(path, site, [{"placeholder": "dây nịt nam", "url": DAY_NIT}])
    assert f"Hãy đọc [dây nịt nam]({DAY_NIT}) trước" in md_of(d)
    assert [p["anchor"] for p in res["left_placeholders"]] == ["máy xay sinh tố"]
    plan = il.suggest(il.load_draft(path), site)
    left = plan["placeholders"][0]
    assert left["anchor"] == "máy xay sinh tố" and left["proposal"] is None


def test_apply_trims_products_over_forty_percent_and_exact_over_one_in_ten(tmp_path, site):
    body = """
Mở bài không có liên kết nào cả.

Ví ngăn bí mật da bò hợp túi sau.

Dây nịt da bò khóa tự động hợp đồ công sở.

Thẻ ví card mỏng đựng thẻ ngân hàng.

Hãy đọc cách bảo quản đồ da bền màu.

Theo hướng dẫn phối màu trang phục nam của shop.
"""
    d = draft_dir(tmp_path, body=body, extra="content_type: how-to-guide\n")
    path = d / "cach-chon-ma-moi.md"
    # the fixture title says "cách chọn", which would make this a buying guide; use another title
    path.write_text(path.read_text(encoding="utf-8").replace(
        "title: Cách chọn ví da nam bền và gọn", "title: Ví da nam trong tủ đồ"), encoding="utf-8")
    plan = [
        {"anchor": "ví ngăn bí mật da bò", "url": PROD_DEN, "paragraph": 1},
        {"anchor": "dây nịt da bò", "url": BASE + "/products/day-nit-da-bo", "paragraph": 2},
        {"anchor": "ví card mỏng đựng thẻ", "url": BASE + "/products/vi-card-mong", "paragraph": 3},
        {"anchor": "cách bảo quản đồ da", "url": BAO_QUAN, "paragraph": 4},
        {"anchor": "phối màu trang phục", "url": PHOI_MAU, "paragraph": 5},
    ]
    res = il.apply_plan(path, site, plan, dry_run=True)
    # 3 products of 5 links is 60% and 2 of 4 is 50%: the latest products go until 1 of 3 (33%) is left
    assert [a["type"] for a in res["applied"]].count("product") == 1
    assert len(res["applied"]) == 3
    assert [r["url"] for r in res["refused"]] == [BASE + "/products/vi-card-mong", BASE + "/products/day-nit-da-bo"]
    assert all("40%" in r["reason"] for r in res["refused"])


def test_cli_suggest_then_apply_round_trip(tmp_path, root, capsys):
    d = draft_dir(tmp_path)
    assert il.main(["suggest", "--draft", str(d), "--site", "cuahang.test", "--target", "5"]) == 0
    plan = json.loads((d / "internal-links-plan.json").read_text(encoding="utf-8"))
    assert plan["links"]
    capsys.readouterr()
    il.main(["apply", "--draft", str(d), "--site", "cuahang.test", "--dry-run"])
    assert "chạy thử" in capsys.readouterr().out
    assert VI_DA_NAM not in md_of(d)
    assert il.main(["apply", "--draft", str(d), "--site", "cuahang.test"]) == 0
    assert all(l["url"] in md_of(d) for l in plan["links"])


# ---------------------------------------------------------------------------
# reverse
# ---------------------------------------------------------------------------

def test_reverse_lists_old_posts_and_never_touches_the_site(tmp_path, site, capsys):
    d = draft_dir(tmp_path)
    inv_before = (site.dir / "inventory.csv").read_bytes()
    draft = il.load_draft(d / "cach-chon-ma-moi.md")
    items = il.reverse_suggestions(site, il.post_info(draft), top=5)
    assert items
    urls = [i["post_url"] for i in items]
    assert GONE not in urls and EXCLUDED not in urls and draft.canonical not in urls
    for i in items:
        assert draft.canonical in i["sentence"] and i["anchor"]
    il.main(["reverse", "--draft", str(d), "--site", "cuahang.test"])
    assert "Tôi không sửa web" in capsys.readouterr().out
    assert (site.dir / "inventory.csv").read_bytes() == inv_before


# ---------------------------------------------------------------------------
# Gate 5
# ---------------------------------------------------------------------------

def gate5_dir(tmp_path, links_md: str, canonical="https://cuahang.test/blogs/cach-chon-ma-moi",
              name="cach-chon-ma-moi"):
    d = tmp_path / name
    d.mkdir()
    (d / f"{name}.md").write_text((FM % "") + "\n# Bài\n\n" + links_md + "\n", encoding="utf-8")
    anchors = "".join(f'<a href="{u}">liên kết</a> ' for u in
                      [m.group(2) for m in il._LINK_RE.finditer(links_md)])
    (d / f"{name}.html").write_text(
        f'<!DOCTYPE html><html><head><link rel="canonical" href="{canonical}">'
        '<script type="application/ld+json">{"@type":"BlogPosting","headline":"x","image":"h.png",'
        '"datePublished":"2026-10-02","author":"A","wordCount":3}</script></head><body><article>'
        f'<p>Một hai ba {anchors}</p>{links_md.replace("[", "(").replace("]", ")") if "INTERNAL" in links_md else ""}'
        '<footer class="post-footer"><a href="https://cuahang.test">Cửa Hàng</a></footer></article></body></html>',
        encoding="utf-8")
    (d / f"{name}.pdf").write_bytes(b"%PDF-1.4")
    return d


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(blog_preflight, "_http_head", lambda url: 200)
    monkeypatch.setattr(blog_preflight, "_safe_http_url", lambda url: (True, None))


def test_gate5_passes_with_inventory_links_and_ignores_footer_home(tmp_path, root, offline):
    d = gate5_dir(tmp_path, f"Xem [ví da nam]({VI_DA_NAM}) và [dây nịt]({DAY_NIT}).")
    res = blog_preflight.gate_5_asset_link_integrity(d, slug="cach-chon-ma-moi")
    assert not [v for v in res["violations"] if "danh sách" in v or "giữ chỗ" in v], res["violations"]
    assert res["site_internal_links"]["site"] == "cuahang.test"
    assert VI_DA_NAM in res["site_internal_links"]["internal_urls"]


def test_gate5_blocks_fake_internal_url_with_vietnamese_message(tmp_path, root, offline):
    fake = BASE + "/products/khong-co-that"
    d = gate5_dir(tmp_path, f"Xem [ví]({VI_DA_NAM}) và [giả]({fake}).")
    res = blog_preflight.gate_5_asset_link_integrity(d, slug="cach-chon-ma-moi")
    msg = next(v for v in res["violations"] if fake in v)
    assert "không có trong danh sách của web cuahang.test" in msg
    assert f"python3 scripts/site_inventory.py add {fake} --site cuahang.test" in msg
    assert res["passed"] is False


def test_gate5_blocks_gone_page_and_placeholder(tmp_path, root, offline):
    d = gate5_dir(tmp_path, f"Xem [cũ]({GONE}).\n\n[INTERNAL-LINK: dây nịt → danh mục]")
    res = blog_preflight.gate_5_asset_link_integrity(d, slug="cach-chon-ma-moi")
    text = " ".join(res["violations"])
    assert "type=gone" in text and "[INTERNAL-LINK: dây nịt → danh mục]" in text
    assert "internal_links.py suggest" in text


def test_gate5_without_a_site_is_unchanged(tmp_path, monkeypatch, offline):
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "none"))
    d = gate5_dir(tmp_path, f"Xem [giả]({BASE}/khong-co) và [INTERNAL-LINK: a → b].")
    res = blog_preflight.gate_5_asset_link_integrity(d, slug="cach-chon-ma-moi")
    assert "site_internal_links" not in res
    assert not any("danh sách của web" in v or "giữ chỗ" in v for v in res["violations"])


def test_gate5_other_host_is_not_checked(tmp_path, root, offline):
    d = gate5_dir(tmp_path, "Xem [giả](https://cuahang.test/khong-co).",
                  canonical="https://khac.test/bai")
    res = blog_preflight.gate_5_asset_link_integrity(d, slug="cach-chon-ma-moi")
    assert "site_internal_links" not in res


# ---------------------------------------------------------------------------
# Draft rubric
# ---------------------------------------------------------------------------

LONG = "\n".join(
    f"Đoạn {i}: Mình thử chiếc ví này trong ba tuần, bỏ vào túi quần mỗi ngày và ghi lại việc mép da có bong không."
    for i in range(1, 30))


def write_post(tmp_path, links: str, canonical="https://cuahang.test/blogs/cach-chon-ma-moi", extra="",
               title="Cách chọn ví da nam bền và gọn"):
    p = tmp_path / "post.md"
    p.write_text(
        FM.replace("https://cuahang.test/blogs/cach-chon-ma-moi", canonical).replace(
            "title: Cách chọn ví da nam bền và gọn", f"title: {title}") % extra
        + "\n# Cách chọn ví da nam bền và gọn\n\n" + links + "\n\n" + LONG + "\n", encoding="utf-8")
    return p


def test_rubric_scores_internal_links_only_with_a_site(tmp_path, root):
    links = (f"Xem [ví da nam]({VI_DA_NAM}), [dây nịt]({DAY_NIT}) và [chính sách đổi trả]({DOI_TRA})\n\n"
             f"Đọc thêm [cách bảo quản đồ da]({BAO_QUAN}).")
    res = analyze_blog.analyze_file(str(write_post(tmp_path, links)), mode="draft")
    item = res["score"]["items"]["internal_links"]
    assert item["applicable"] and item["score"] > 0
    assert res["links"]["internal_count"] == 4              # absolute links to the site host count
    assert "internal_links" not in [r["item"] for r in res["score"]["prepublish_checklist"]]
    assert "site_links" in res["score"]["categories"]


def test_rubric_penalises_unresolved_placeholder_unknown_url_and_products(tmp_path, root):
    links = (f"[INTERNAL-LINK: a → b] [giả]({BASE}/khong-co) [ví]({PROD_DEN})\n\n"
             f"[dây nịt da bò]({BASE}/products/day-nit-da-bo)")
    res = analyze_blog.analyze_file(
        str(write_post(tmp_path, links, title="Ví da nam trong tủ đồ")), mode="draft")
    item = res["score"]["items"]["internal_links"]
    assert item["score"] <= 3                                # placeholder caps the count at 1; 2 of 4 are products
    issues = " ".join(i["issue"] for i in res["score"]["issues"])
    assert "giữ chỗ" in issues and BASE + "/khong-co" in issues and "quá 40%" in issues


def test_rubric_without_a_site_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "none"))
    p = write_post(tmp_path, f"Xem [ví da nam]({VI_DA_NAM}).")
    res = analyze_blog.analyze_file(str(p), mode="draft")
    assert "internal_links" not in res["score"]["items"]
    assert "site_links" not in res and res["links"]["internal_count"] == 0
    assert "internal_links" in [r["item"] for r in res["score"]["prepublish_checklist"]]
    assert "site_links" not in res["score"]["categories"]
    assert draft_rubric.WEIGHTS and sum(draft_rubric.WEIGHTS.values()) == 100


# ---------------------------------------------------------------------------
# publish_cms hook
# ---------------------------------------------------------------------------

def make_post(canonical):
    return publish_cms.Post(title="Cách chọn ví da nam bền và gọn", slug="cach-chon-ma-moi",
                            description="Hướng dẫn.", html="<p>x</p>", canonical=canonical,
                            categories=["Ví da"])


def test_publish_hook_adds_url_and_prints_reverse(tmp_path, root):
    d = draft_dir(tmp_path)
    md = d / "cach-chon-ma-moi.md"
    out: list = []
    result = publish_cms.Result("wordpress", "7", "publish", "https://cms.test/?p=7", "edit")
    publish_cms.record_in_inventory(d, md, make_post("https://cuahang.test/blogs/cach-chon-ma-moi"),
                                    {"focus_keyword": "chọn ví da nam"}, result, out=out.append)
    rows = {r["url"]: r for r in si.load_inventory(root / "cuahang.test")}
    row = rows["https://cuahang.test/blogs/cach-chon-ma-moi"]
    assert row["type"] == "post" and row["focus_keyword"] == "chọn ví da nam"
    assert any("Bài cũ nên trỏ về bài mới" in o for o in out)


def test_publish_hook_failure_never_raises(tmp_path, root, monkeypatch, capsys):
    d = draft_dir(tmp_path)
    monkeypatch.setattr(si, "cmd_add", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ổ đĩa đầy")))
    result = publish_cms.Result("wordpress", "7", "publish", "https://cms.test/?p=7", "edit")
    publish_cms.record_in_inventory(d, d / "cach-chon-ma-moi.md",
                                    make_post("https://cuahang.test/blogs/cach-chon-ma-moi"),
                                    {}, result, out=lambda *_: None)
    assert "chưa ghi được vào danh sách web" in capsys.readouterr().err


def test_publish_hook_ignores_posts_on_other_hosts(tmp_path, root):
    d = draft_dir(tmp_path)
    before = (root / "cuahang.test" / "inventory.csv").read_bytes()
    result = publish_cms.Result("wordpress", "7", "publish", "https://cms.test/?p=7", "edit")
    publish_cms.record_in_inventory(d, d / "cach-chon-ma-moi.md", make_post("https://khac.test/bai"),
                                    {}, result, out=lambda *_: None)
    assert (root / "cuahang.test" / "inventory.csv").read_bytes() == before


def test_run_records_only_after_a_live_publish(tmp_path, root, monkeypatch, capsys):
    """Dry run and draft never touch the inventory; a live publish does."""
    d = draft_dir(tmp_path)
    (d / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeClient:
        def __init__(self, **_):
            pass

        def missing(self):
            return []

        def publish(self, post, live):
            return publish_cms.Result("wordpress", "9", "publish" if live else "draft",
                                      "https://cms.test/?p=9", "https://cms.test/edit")

    monkeypatch.setitem(publish_cms.CLIENTS, "wordpress", FakeClient)
    monkeypatch.setattr(publish_cms, "notify_indexnow", lambda url: "IndexNow: bỏ qua")
    monkeypatch.setattr(publish_cms, "preflight", lambda *a, **k: ([], [], "source"))
    inv = root / "cuahang.test" / "inventory.csv"
    before = inv.read_bytes()
    assert publish_cms.main(["--draft", str(d), "--dry-run", "--publish"]) == 0
    assert publish_cms.main(["--draft", str(d)]) == 0                    # draft
    assert inv.read_bytes() == before
    assert publish_cms.main(["--draft", str(d), "--publish"]) == 0
    assert "https://cuahang.test/blogs/cach-chon-ma-moi" in inv.read_text(encoding="utf-8")
    assert "Đã thêm bài vào danh sách" in capsys.readouterr().out
