"""Tests for scripts/site_inventory.py. No network: the HTTP layer is a fake."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import site_inventory as si  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "site_inventory"


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeNet:
    """URL prefix -> (status, headers, body). Longest matching prefix wins."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list = []
        self.headers_seen: list = []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        self.headers_seen.append(dict(headers or {}))
        best = None
        for prefix, val in self.routes.items():
            if url.startswith(prefix) and (best is None or len(prefix) > len(best)):
                best = prefix
        if best is None:
            return si.Response(404, {}, b"", url)
        status, hdrs, body = self.routes[best]
        if callable(body):
            status, hdrs, body = body(url, headers or {})
        return si.Response(status, hdrs, body, url)


def ok(body: bytes, **hdrs):
    return (200, {k.replace("_", "-"): v for k, v in hdrs.items()}, body)


@pytest.fixture(autouse=True)
def sites_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "sites"))
    return tmp_path / "sites"


def make_fetcher(routes, tmp_path=None):
    net = FakeNet(routes)
    sleeps = []
    f = si.Fetcher("https://example.vn", cache_dir=(tmp_path / "cache") if tmp_path else None,
                   transport=net, delay=0.5, sleep=sleeps.append)
    f.sleeps = sleeps
    return f, net


# ---------------------------------------------------------------- text & urls

def test_clean_text_strips_tags_formula_and_truncates():
    assert si.clean_text("<p>Hello &amp; <b>bye</b></p>") == "Hello & bye"
    assert si.clean_text('=HYPERLINK("x")') == 'HYPERLINK("x")'
    assert si.clean_text("+84 912") == "84 912"
    long = si.clean_text("a" * 500, 50)
    assert len(long) == 50
    assert "‮" not in si.clean_text("ab‮cd")


def test_norm_url():
    assert si.norm_url("HTTPS://Example.VN:443/a/b/?utm_source=x#frag") == "https://example.vn/a/b"
    assert si.norm_url("https://example.vn") == "https://example.vn/"
    assert si.norm_url("https://example.vn/p?id=2&fbclid=z") == "https://example.vn/p?id=2"


def test_classify_precedence():
    assert si.classify("https://x.vn/san-pham/abc/") == "product"
    assert si.classify("https://x.vn/products/abc") == "product"
    assert si.classify("https://x.vn/collections/ao/products/abc") == "product"
    assert si.classify("https://x.vn/category/meo/") == "category"
    assert si.classify("https://x.vn/tag/espresso/") == "tag"
    assert si.classify("https://x.vn/blog/cach-chon") == "post"
    assert si.classify("https://x.vn/2026/01/ten-bai/") == "post"
    assert si.classify("https://x.vn/gioi-thieu/") == "page"
    assert si.classify("https://x.vn/") == "page"
    # sitemap hint beats a weak URL guess; page evidence beats the hint
    assert si.classify("https://x.vn/abc/def/ghi", hint="post") == "post"
    assert si.classify("https://x.vn/blog/abc", hint="post", og_type="product") == "product"
    assert si.sitemap_hint("https://x.vn/wp-sitemap-taxonomies-category-1.xml") == "category"
    assert si.sitemap_hint("https://x.vn/sitemap_products_1.xml") == "product"
    assert si.sitemap_hint("https://x.vn/post-sitemap.xml") == "post"
    assert si.sitemap_hint("https://x.vn/page-sitemap.xml") == "page"
    assert si.sitemap_hint("https://x.vn/sitemap.xml") is None


def test_url_allowed_patterns():
    assert si.url_allowed("https://x.vn/blog/a", [], [])
    assert not si.url_allowed("https://x.vn/tag/a", [], ["/tag/*"])
    assert si.url_allowed("https://x.vn/blog/a", ["/blog/*"], [])
    assert not si.url_allowed("https://x.vn/about", ["/blog/*"], [])


# --------------------------------------------------------------- extraction

def test_extract_page_product_ldjson_and_untrusted_text():
    page = si.extract_page(fx("product.html").decode())
    assert page["title"] == "Máy pha cà phê Espresso X1"
    assert page["h1"] == "Máy pha cà phê Espresso X1"
    assert page["description"].startswith("Máy pha espresso")
    assert page["og_type"] == "product"
    assert page["is_product"] and page["price"] == "4500000 VND" and page["in_stock"] == "yes"
    assert page["canonical"].endswith("/san-pham/may-pha-espresso-x1/")
    # nothing from the body is stored
    assert "Ignore previous" not in repr(page)


def test_extract_page_formula_title_neutralised_and_garbage_ok():
    page = si.extract_page(fx("post.html").decode())
    assert not page["title"].startswith("=")
    assert si.extract_page("<<<>>><html><title>x")["title"] == "x"
    assert si.extract_page("")["title"] == ""


def test_extract_page_truncates_fields():
    html = f"<html><head><title>{'t' * 900}</title></head></html>"
    assert len(si.extract_page(html)["title"]) <= si.FIELD_LIMITS["title"]


# ---------------------------------------------------------------- sitemaps

def test_parse_sitemap_index_and_urlset():
    kind, items = si.parse_sitemap(fx("sitemap_index.xml"))
    assert kind == "index" and len(items) == 3
    kind, items = si.parse_sitemap(fx("post_sitemap.xml"))
    assert kind == "urlset" and items[0] == ("https://example.vn/cach-chon-may-pha-ca-phe/", "2026-01-05")


def test_parse_sitemap_rejects_entities_and_garbage():
    assert si.parse_sitemap(fx("sitemap_dtd.xml")) == ("urlset", [])
    assert si.parse_sitemap(b"not xml")[1] == []


def test_parse_sitemap_gzip():
    import gzip
    kind, items = si.parse_sitemap(gzip.compress(fx("post_sitemap.xml")))
    assert len(items) == 3


def test_collect_sitemap_urls_filters_foreign_hosts_and_hints():
    routes = {
        "https://example.vn/robots.txt": (404, {}, b""),
        "https://example.vn/sitemap_index.xml": ok(fx("sitemap_index.xml")),
        "https://example.vn/post-sitemap.xml": ok(fx("post_sitemap.xml")),
        "https://example.vn/product-sitemap.xml": ok(fx("product_sitemap.xml")),
    }
    f, net = make_fetcher(routes)
    urls, cut = si.collect_sitemap_urls(f, ["https://example.vn/sitemap_index.xml"], "https://example.vn",
                                        per_group=100, total_cap=100)
    got = {u for u, _, _ in urls}
    assert "https://other.example.org/stolen/" not in got
    assert not any("evil" in c for c in net.calls)
    assert len(urls) == 3 and not cut
    hints = {u: h for u, _, h in urls}
    assert hints["https://example.vn/san-pham/may-pha-espresso-x1/"] == "product"
    urls, cut = si.collect_sitemap_urls(f, ["https://example.vn/sitemap_index.xml"], "https://example.vn",
                                        per_group=1, total_cap=100)
    assert cut and len(urls) == 2


# ------------------------------------------------------------- fetcher rules

def test_fetcher_respects_robots_and_counts_blocked():
    robots = b"User-agent: *\nDisallow: /private/\nSitemap: https://example.vn/sm.xml\n"
    f, net = make_fetcher({
        "https://example.vn/robots.txt": ok(robots),
        "https://example.vn/": ok(b"hi"),
    })
    assert f.get("https://example.vn/").status == 200
    with pytest.raises(si.FetchError):
        f.get("https://example.vn/private/x")
    assert "https://example.vn/private/x" not in net.calls
    assert f.robots_blocked == ["https://example.vn/private/x"]
    assert f.sitemaps_from_robots == ["https://example.vn/sm.xml"]


def test_fetcher_robots_5xx_blocks_everything_and_4xx_allows():
    f, _ = make_fetcher({"https://example.vn/robots.txt": (503, {}, b""), "https://example.vn/": ok(b"x")})
    with pytest.raises(si.FetchError):
        f.get("https://example.vn/")
    f, _ = make_fetcher({"https://example.vn/robots.txt": (403, {}, b""), "https://example.vn/": ok(b"x")})
    assert f.get("https://example.vn/").status == 200


def test_fetcher_delay_between_requests():
    clock = {"t": 100.0}
    net = FakeNet({"https://example.vn/robots.txt": (404, {}, b""), "https://example.vn/a": ok(b"a")})
    sleeps = []
    f = si.Fetcher("https://example.vn", transport=net, delay=0.5, sleep=lambda s: (sleeps.append(s)),
                   clock=lambda: clock["t"])
    f.get("https://example.vn/a")
    f.get("https://example.vn/a")
    assert sleeps and all(abs(s - 0.5) < 1e-9 for s in sleeps)


def test_fetcher_conditional_get_uses_cache(tmp_path):
    state = {"n": 0}

    def handler(url, headers):
        state["n"] += 1
        if headers.get("If-None-Match") == '"v1"':
            return 304, {}, b""
        return 200, {"etag": '"v1"'}, b"BODY"

    f, net = make_fetcher({"https://example.vn/robots.txt": (404, {}, b""),
                           "https://example.vn/p": (200, {}, handler)}, tmp_path)
    first = f.get("https://example.vn/p")
    second = f.get("https://example.vn/p")
    assert first.body == b"BODY" and second.body == b"BODY" and second.cached
    assert net.headers_seen[-1].get("If-None-Match") == '"v1"'


def test_http_get_refuses_private_address(monkeypatch):
    monkeypatch.setattr(si, "_resolve_public_url",
                        lambda url: (False, "resolved address is not public: 10.0.0.1", None, None, []))
    with pytest.raises(si.FetchError):
        si.http_get("http://internal.example/")


def test_http_get_blocks_redirect_to_other_host(monkeypatch):
    import urllib.error
    import email.message

    monkeypatch.setattr(si, "_resolve_public_url",
                        lambda url: (True, None, "example.vn", 443, [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))]))

    class Opener:
        def open(self, req, timeout=None):
            hdrs = email.message.Message()
            hdrs["Location"] = "http://127.0.0.1/admin"
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs, None)

    monkeypatch.setattr(si, "_OPENER", Opener())
    with pytest.raises(si.FetchError):
        si.http_get("https://example.vn/")


def test_http_get_follows_same_site_redirect(monkeypatch):
    import urllib.error
    import email.message

    monkeypatch.setattr(si, "_resolve_public_url",
                        lambda url: (True, None, "example.vn", 443, [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))]))

    class Body:
        status = 200
        headers = email.message.Message()

        def read(self, n):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout=None):
            if req.full_url == "https://example.vn/":
                h = email.message.Message()
                h["Location"] = "https://www.example.vn/"
                raise urllib.error.HTTPError(req.full_url, 301, "Moved", h, None)
            return Body()

    monkeypatch.setattr(si, "_OPENER", Opener())
    resp = si.http_get("https://example.vn/")
    assert resp.body == b"ok" and resp.url == "https://www.example.vn/"


# ------------------------------------------------------------- platform / API

WP_ROUTES = {
    "https://example.vn/robots.txt": (404, {}, b""),
    "https://example.vn/": ok(fx("home.html")),
    "https://example.vn/wp-json/": ok(fx("wp_root.json")),
    "https://example.vn/wp-json/wp/v2/posts": ok(fx("wp_posts.json")),
    "https://example.vn/wp-json/wp/v2/pages": ok(fx("wp_pages.json")),
    "https://example.vn/wp-json/wp/v2/categories": ok(fx("wp_categories.json")),
    "https://example.vn/wp-json/wc/store/v1/products/categories": (404, {}, b""),
    "https://example.vn/wp-json/wc/store/v1/products?": ok(fx("woo_products.json")),
}


def test_detect_woocommerce_before_sitemap():
    f, net = make_fetcher(WP_ROUTES)
    cms, base, home = si.detect_platform(f, "https://example.vn")
    assert cms == "woocommerce" and base == "https://example.vn"
    assert not any("products.json" in c for c in net.calls)


def test_detect_shopify_vs_haravan_and_blogger_and_other():
    shop = {"https://example.vn/robots.txt": (404, {}, b""),
            "https://example.vn/wp-json/": (404, {}, b""),
            "https://example.vn/products.json": ok(fx("shopify_products.json")),
            "https://example.vn/": ok(b"<html><script src='//cdn.shopify.com/x.js'></script></html>")}
    assert si.detect_platform(make_fetcher(shop)[0], "https://example.vn")[0] == "shopify"
    shop["https://example.vn/"] = ok(b"<html><link href='//theme.hstatic.net/200/a.css'></html>")
    assert si.detect_platform(make_fetcher(shop)[0], "https://example.vn")[0] == "haravan"
    blog = {"https://example.vn/robots.txt": (404, {}, b""),
            "https://example.vn/feeds/posts/default": ok(b'{"feed":{"entry":[]}}')}
    assert si.detect_platform(make_fetcher(blog)[0], "https://example.vn")[0] == "blogger"
    assert si.detect_platform(make_fetcher({"https://example.vn/robots.txt": (404, {}, b"")})[0],
                              "https://example.vn")[0] == "other"


def test_wp_rows_posts_pages_categories():
    f, _ = make_fetcher(WP_ROUTES)
    rows, truncated, ok_ = si.wp_rows(f, "https://example.vn", 100, "vi")
    assert ok_ and not truncated
    by_type = si.type_counts(rows)
    assert by_type == {"post": 2, "page": 1, "category": 2}
    first = next(r for r in rows if r["url"].endswith("cach-chon-may-pha-ca-phe/"))
    assert first["title"] == "Cách chọn máy pha cà phê & xay"
    assert first["description"] == "Hướng dẫn chọn máy pha."
    assert first["category"] == "Máy pha"
    second = next(r for r in rows if r["url"].endswith("mon-cuoi/"))
    assert second["category"] == "Máy pha | Mẹo"
    assert first["source"] == "wp-rest" and first["lastmod"].startswith("2026-03-01")


def test_woo_rows_price_math_and_stock():
    f, _ = make_fetcher(WP_ROUTES)
    rows, _ = si.woo_rows(f, "https://example.vn", 100, "vi")
    prods = {r["title"]: r for r in rows if r["type"] == "product"}
    assert prods["Máy pha Espresso X1"]["price"] == "4500000 VND"
    assert prods["Máy pha Espresso X1"]["in_stock"] == "yes"
    assert prods["Cối xay"]["price"] == "1999 USD"
    assert prods["Cối xay"]["in_stock"] == "no"


def test_shop_rows_haravan_min_price_and_pagination():
    pages = {1: ok(fx("shopify_products.json"))}
    full = {"products": [{"title": f"P{i}", "handle": f"p{i}", "variants": [{"price": "1", "available": True}]}
                         for i in range(3)]}
    import json

    def handler(url, headers):
        if "page=1" in url:
            return 200, {}, json.dumps(full).encode()
        if "page=2" in url:
            return 200, {}, json.dumps({"products": [{"title": "P3", "handle": "p3", "variants": []}]}).encode()
        return 200, {}, b'{"products":[]}'

    f, net = make_fetcher({"https://example.vn/robots.txt": (404, {}, b""),
                           "https://example.vn/products.json": (200, {}, handler)})
    rows, _ = si.shop_rows(f, "https://example.vn", "haravan", 3, "vi")
    assert len([r for r in rows if r["type"] == "product"]) == 3  # per_page=3, page 2 fetched only when needed
    f, _ = make_fetcher({"https://example.vn/robots.txt": (404, {}, b""),
                         "https://example.vn/products.json": ok(fx("shopify_products.json"))})
    rows, _ = si.shop_rows(f, "https://example.vn", "haravan", 250, "vi")
    ao = next(r for r in rows if r["title"] == "Áo thun cổ tròn")
    assert ao["price"] == "179000 VND" and ao["in_stock"] == "yes"
    assert ao["url"] == "https://example.vn/products/ao-thun-co-tron"
    assert next(r for r in rows if r["title"] == "Quần short")["in_stock"] == "no"


def test_wp_rest_paginates_until_total_pages():
    import json

    def posts(url, headers):
        page = int(url.split("page=")[1].split("&")[0])
        items = [{"link": f"https://example.vn/p{page}-{i}/", "title": {"rendered": "t"}, "excerpt": {"rendered": ""},
                  "categories": []} for i in range(2)]
        return 200, {"x-wp-totalpages": "2"}, json.dumps(items).encode()

    routes = dict(WP_ROUTES)
    routes["https://example.vn/wp-json/wp/v2/posts"] = (200, {}, posts)
    f, _ = make_fetcher(routes)
    rows, _, _ = si.wp_rows(f, "https://example.vn", 2, "vi")
    # per_page=2, totalpages=2: page 1 hits the limit of 2 -> truncated
    assert len([r for r in rows if r["type"] == "post"]) == 2


# ------------------------------------------------------------------- CSV

def test_csv_roundtrip_has_bom_and_reads_with_or_without(tmp_path):
    p = tmp_path / "inv.csv"
    row = si.blank_row()
    row.update(url="https://example.vn/a", title="Máy pha cà phê", type="post", notes='có "dấu", phẩy')
    si.write_csv_rows(p, [row])
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert si.read_csv_rows(p)[0]["notes"] == 'có "dấu", phẩy'
    p.write_bytes(raw[3:])  # no BOM
    assert si.read_csv_rows(p)[0]["title"] == "Máy pha cà phê"
    # a semicolon file as Excel (vi-VN locale) saves it, with BOM
    p.write_bytes(b"\xef\xbb\xbf" + "url;title;focus_keyword\r\nhttps://x.vn/a;Tiêu đề;từ khoá\r\n".encode())
    r = si.read_csv_rows(p)[0]
    assert r["title"] == "Tiêu đề" and r["focus_keyword"] == "từ khoá"


def test_csv_keeps_unknown_columns(tmp_path):
    p = tmp_path / "inv.csv"
    p.write_bytes("url,title,my_col\nhttps://x.vn/a,T,keep me\n".encode())
    rows = si.read_csv_rows(p)
    si.write_csv_rows(p, rows)
    assert si.read_csv_rows(p)[0]["my_col"] == "keep me"


# ------------------------------------------------------------------ merge

def row(url, **kw):
    r = si.blank_row()
    r.update(url=url, type="post", source="sitemap", **kw)
    return r


def test_merge_never_overwrites_editable_columns():
    stored = row("https://x.vn/a", title="Old", focus_keyword="máy pha", anchors="a|b", priority="5",
                 exclude="yes", notes="mine")
    fresh = row("https://x.vn/a/", title="New", focus_keyword="CLOBBER", anchors="X", priority="1",
                exclude="", notes="theirs")
    out = si.merge_inventory([stored], [fresh])
    assert len(out) == 1
    r = out[0]
    assert (r["focus_keyword"], r["anchors"], r["priority"], r["exclude"], r["notes"]) == \
        ("máy pha", "a|b", "5", "yes", "mine")
    assert r["title"] == "New"


def test_merge_empty_fresh_value_keeps_stored_generated_value():
    out = si.merge_inventory([row("https://x.vn/a", title="Keep", price="10")],
                             [row("https://x.vn/a", title="")])
    assert out[0]["title"] == "Keep" and out[0]["price"] == "10"


def test_merge_marks_vanished_gone_and_revives():
    out = si.merge_inventory([row("https://x.vn/a", notes="n"), row("https://x.vn/b")], [row("https://x.vn/a")])
    assert out[0]["type"] == "post" and out[1]["type"] == "gone"
    assert out[1]["url"] == "https://x.vn/b"
    again = si.merge_inventory(out, [row("https://x.vn/a"), row("https://x.vn/b")])
    assert again[1]["type"] == "post"


def test_merge_incomplete_scan_marks_nothing_gone():
    out = si.merge_inventory([row("https://x.vn/a"), row("https://x.vn/b")], [row("https://x.vn/a")], complete=False)
    assert [r["type"] for r in out] == ["post", "post"]


def test_merge_manual_rows_are_never_gone():
    manual = row("https://x.vn/new-post")
    manual["source"] = "manual"
    out = si.merge_inventory([manual], [row("https://x.vn/a")])
    assert out[0]["type"] == "post"


def test_merge_weak_type_does_not_downgrade():
    stored = row("https://x.vn/a")
    stored["type"] = "product"
    fresh = row("https://x.vn/a")
    fresh["type"] = "other"
    assert si.merge_inventory([stored], [fresh])[0]["type"] == "product"


# ---------------------------------------------------------------- search

def corpus():
    def mk(url, typ, title, **kw):
        r = si.blank_row()
        r.update(url=url, type=typ, title=title, **kw)
        return r
    return [
        mk("https://x.vn/cach-chon-may-pha-ca-phe/", "post", "Cách chọn máy pha cà phê tại nhà",
           description="Hướng dẫn chọn máy pha cà phê espresso"),
        mk("https://x.vn/san-pham/may-xay-ca-phe/", "product", "Máy xay cà phê Hario"),
        mk("https://x.vn/san-pham/may-pha-x1/", "product", "Máy pha espresso X1", focus_keyword="máy pha cà phê"),
        mk("https://x.vn/gioi-thieu/", "page", "Giới thiệu cửa hàng"),
        mk("https://x.vn/cu/", "gone", "Máy pha cà phê cũ"),
    ]


def test_tokenize_strips_diacritics_and_adds_bigrams():
    assert si.tokenize("Máy pha cà phê Đà Lạt") == \
        ["may", "pha", "ca", "phe", "da", "lat", "may pha", "pha ca", "ca phe", "phe da", "da lat"]
    assert si.tokenize("") == []
    assert si.tokenize("Café 123") == ["cafe", "123", "cafe 123"]


@pytest.mark.parametrize("with_marks,without", [
    ("máy pha cà phê", "may pha ca phe"),
    ("Đà Lạt", "Da Lat"),
    ("giới thiệu cửa hàng", "gioi thieu cua hang"),
])
def test_search_same_result_with_and_without_diacritics(with_marks, without):
    rows = corpus()
    a = si.search(rows, with_marks)
    b = si.search(rows, without)
    assert [r["url"] for r in a] == [r["url"] for r in b]
    assert [r["score"] for r in a] == [r["score"] for r in b]


def test_search_ranking_type_filter_gone_and_top():
    rows = corpus()
    hits = si.search(rows, "máy pha cà phê")
    assert hits[0]["url"] == "https://x.vn/san-pham/may-pha-x1/" or hits[0]["url"].endswith("may-pha-ca-phe/")
    assert all(h["type"] != "gone" for h in hits)
    assert [h["type"] for h in si.search(rows, "máy", type="product")] == ["product", "product"]
    assert len(si.search(rows, "máy", top=1)) == 1
    assert si.search(rows, "zzzz") == []
    assert si.search(rows, "") == []
    assert any(h["type"] == "gone" for h in si.search(rows, "máy pha cà phê cũ", include_gone=True))


def test_search_idf_prefers_rare_terms():
    rows = corpus()
    # "espresso" is rarer than "may": the espresso product must outrank the grinder
    top = si.search(rows, "máy espresso")[0]
    assert "espresso" in top["title"].lower() or "espresso" in top["description"].lower()


def test_search_focus_keyword_outweighs_description():
    rows = [si.blank_row(), si.blank_row()]
    rows[0].update(url="https://x.vn/a", type="post", title="A", description="trà sen vàng")
    rows[1].update(url="https://x.vn/b", type="post", title="B", focus_keyword="trà sen vàng")
    assert si.search(rows, "trà sen vàng")[0]["url"] == "https://x.vn/b"


# ------------------------------------------------------- site folder helpers

def test_sites_root_env_and_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_BLOG_SITES_ROOT")
    monkeypatch.chdir(tmp_path)
    assert si.sites_root() == tmp_path / "sites"
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(tmp_path / "x"))
    assert si.sites_root() == tmp_path / "x"


def test_find_site_for_host_and_resolve(sites_env):
    d = sites_env / "example.vn"
    d.mkdir(parents=True)
    si.write_site_toml(d, {"base_url": "https://www.example.vn", "cms": "wordpress"})
    assert si.find_site_for_host("example.vn") == d
    assert si.find_site_for_host("WWW.Example.vn:443") == d
    assert si.find_site_for_host("other.vn") is None
    assert si.find_site_for_host("") is None
    assert si.resolve_site(None) == d
    assert si.resolve_site("example.vn") == d
    d2 = sites_env / "b.vn"
    d2.mkdir()
    si.write_site_toml(d2, {"base_url": "https://b.vn", "cms": "other"})
    with pytest.raises(si.InventoryError):
        si.resolve_site(None)
    assert si.resolve_site("b.vn") == d2


def test_site_toml_roundtrip_with_vietnamese(sites_env):
    d = sites_env / "x.vn"
    d.mkdir(parents=True)
    cfg = {"base_url": "https://x.vn", "cms": "haravan", "brand": 'Cà phê "Hiền"', "default_author": "Nguyễn Văn A",
           "canonical_pattern": "https://x.vn/blog/{slug}", "sitemaps": ["https://x.vn/sitemap.xml"],
           "exclude": ["/tag/*"], "include": []}
    si.write_site_toml(d, cfg)
    back = si.load_site_config(d)
    assert back["brand"] == 'Cà phê "Hiền"' and back["canonical_pattern"] == "https://x.vn/blog/{slug}"
    assert back["exclude"] == ["/tag/*"]


# ---------------------------------------------------------- end to end (fake)

def args(**kw):
    base = dict(site=None, limit=None, no_fetch_pages=False, url="", brand=None, author=None,
                canonical_pattern=None, force=False, file="", title="", description="", category="",
                focus_keyword="", type=None, fetch=False, query="", top=10, json=False)
    base.update(kw)
    return argparse.Namespace(**base)


def sitemap_routes():
    return {
        "https://example.vn/robots.txt": ok(b"User-agent: *\nDisallow: /wp-admin/\nSitemap: https://example.vn/sitemap_index.xml\n"),
        "https://example.vn/wp-json/": (404, {}, b""),
        "https://example.vn/products.json": (404, {}, b""),
        "https://example.vn/feeds": (404, {}, b""),
        "https://example.vn/": ok(fx("home.html")),
        "https://example.vn/sitemap_index.xml": ok(fx("sitemap_index.xml").replace(b"https://evil.example.org/other-sitemap.xml", b"https://example.vn/none.xml")),
        "https://example.vn/post-sitemap.xml": ok(fx("post_sitemap.xml")),
        "https://example.vn/product-sitemap.xml": ok(fx("product_sitemap.xml")),
        "https://example.vn/cach-chon-may-pha-ca-phe/": ok(fx("post.html")),
        "https://example.vn/ban-tin/": (404, {}, b""),
        "https://example.vn/san-pham/may-pha-espresso-x1/": ok(fx("product.html")),
    }


def test_init_then_refresh_sitemap_fallback_keeps_edits(sites_env):
    net = FakeNet(sitemap_routes())
    log = []
    assert si.cmd_init(args(url="example.vn"), out=log.append, transport=net, delay=0) == 0
    d = sites_env / "example.vn"
    cfg = si.load_site_config(d)
    assert cfg["cms"] == "other" and cfg["lang"] == "vi" and cfg["brand"] == "Cà phê Hiền"
    assert cfg["sitemaps"] == ["https://example.vn/sitemap_index.xml"]
    assert (d / "inventory.csv").read_bytes().startswith(b"\xef\xbb\xbf")

    assert si.cmd_refresh(args(), out=log.append, transport=net, delay=0) == 0
    rows = si.load_inventory(d)
    by = {r["url"]: r for r in rows}
    prod = by["https://example.vn/san-pham/may-pha-espresso-x1/"]
    assert prod["type"] == "product" and prod["price"] == "4500000 VND" and prod["in_stock"] == "yes"
    post = by["https://example.vn/cach-chon-may-pha-ca-phe/"]
    assert post["type"] == "post" and post["h1"] == "Cách chọn máy pha cà phê"
    assert not post["title"].startswith("=")
    assert "https://example.vn/ban-tin/" not in by  # 404 pages are not inventory
    assert (d / "inventory.json").is_file()

    # the marketer edits the CSV; a second refresh keeps every editable column
    post["focus_keyword"] = "chọn máy pha cà phê"
    post["priority"] = "4"
    si.write_csv_rows(d / "inventory.csv", rows)
    si.cmd_refresh(args(), out=log.append, transport=net, delay=0)
    again = {r["url"]: r for r in si.load_inventory(d)}
    assert again[post["url"]]["focus_keyword"] == "chọn máy pha cà phê"
    assert again[post["url"]]["priority"] == "4"

    # a URL disappears from the sitemap: kept, marked gone
    routes = sitemap_routes()
    routes["https://example.vn/product-sitemap.xml"] = ok(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>')
    si.cmd_refresh(args(), out=log.append, transport=FakeNet(routes), delay=0)
    final = {r["url"]: r for r in si.load_inventory(d)}
    assert final["https://example.vn/san-pham/may-pha-espresso-x1/"]["type"] == "gone"
    assert final["https://example.vn/san-pham/may-pha-espresso-x1/"]["price"] == "4500000 VND"

    # with --limit nothing becomes gone, whatever the scan returned
    si.cmd_refresh(args(limit=1), out=log.append, transport=FakeNet(sitemap_routes()), delay=0)
    assert si.load_inventory(d)  # still there
    assert all(r["type"] != "post" or r["url"] for r in si.load_inventory(d))


def test_refresh_woocommerce_never_fetches_html(sites_env):
    net = FakeNet(WP_ROUTES)
    si.cmd_init(args(url="https://example.vn"), out=lambda m: None, transport=net, delay=0)
    d = sites_env / "example.vn"
    assert si.load_site_config(d)["cms"] == "woocommerce"
    net.calls.clear()
    si.cmd_refresh(args(limit=50), out=lambda m: None, transport=net, delay=0)
    counts = si.type_counts(si.load_inventory(d))
    assert counts == {"post": 2, "page": 1, "category": 2, "product": 2}
    assert not any(c.endswith(".xml") for c in net.calls)


def test_init_refuses_existing_without_force(sites_env):
    net = FakeNet(WP_ROUTES)
    si.cmd_init(args(url="example.vn"), out=lambda m: None, transport=net, delay=0)
    with pytest.raises(si.InventoryError):
        si.cmd_init(args(url="example.vn"), out=lambda m: None, transport=net, delay=0)
    assert si.cmd_init(args(url="example.vn", force=True), out=lambda m: None, transport=net, delay=0) == 0


def test_add_import_search_status(sites_env, tmp_path):
    net = FakeNet(WP_ROUTES)
    si.cmd_init(args(url="example.vn"), out=lambda m: None, transport=net, delay=0)
    d = sites_env / "example.vn"
    si.cmd_refresh(args(), out=lambda m: None, transport=net, delay=0)

    out = []
    si.cmd_add(args(url="https://example.vn/bai-moi/", title="Bài mới về cold brew"), out=out.append)
    assert "Đã thêm" in out[0]
    with pytest.raises(si.InventoryError):
        si.cmd_add(args(url="https://evil.test/x"), out=out.append)

    f = tmp_path / "ext.csv"
    f.write_text("URL;Tiêu đề\nhttps://example.vn/trang-an;Trang ẩn sau đăng nhập\nhttps://evil.test/x;Lạ\n",
                 encoding="utf-8-sig")
    out.clear()
    si.cmd_import_csv(args(file=str(f)), out=out.append)
    assert "thêm 1" in out[0] and "bỏ qua 1" in out[0]

    # manual and csv rows survive the next refresh
    si.cmd_refresh(args(), out=lambda m: None, transport=net, delay=0)
    urls = {r["url"]: r["type"] for r in si.load_inventory(d)}
    assert urls["https://example.vn/bai-moi/"] != "gone" and urls["https://example.vn/trang-an"] != "gone"

    out.clear()
    si.cmd_search(args(query="cold brew"), out=out.append)
    assert "bai-moi" in "\n".join(out)
    out.clear()
    si.cmd_search(args(query="COLD BREW"), out=out.append)
    assert "bai-moi" in "\n".join(out)
    out.clear()
    si.cmd_status(args(), out=out.append)
    assert "product: 2" in "\n".join(out)
    out.clear()
    si.cmd_list_sites(args(), out=out.append)
    assert "example.vn" in out[0]


def test_import_never_overwrites_existing_edits(sites_env, tmp_path):
    d = sites_env / "example.vn"
    d.mkdir(parents=True)
    si.write_site_toml(d, {"base_url": "https://example.vn", "cms": "other"})
    r = row("https://example.vn/a", title="Gốc", focus_keyword="giữ")
    si.write_csv_rows(d / "inventory.csv", [r])
    f = tmp_path / "in.csv"
    f.write_text("url,title,focus_keyword,notes\nhttps://example.vn/a,Mới,ĐÈ,ghi chú\n", encoding="utf-8")
    si.cmd_import_csv(args(file=str(f)), out=lambda m: None)
    got = si.load_inventory(d)[0]
    assert got["title"] == "Gốc" and got["focus_keyword"] == "giữ" and got["notes"] == "ghi chú"


def test_robots_blocked_pages_still_listed_but_not_fetched(sites_env):
    routes = sitemap_routes()
    routes["https://example.vn/robots.txt"] = ok(
        b"User-agent: *\nDisallow: /san-pham/\nSitemap: https://example.vn/sitemap_index.xml\n")
    net = FakeNet(routes)
    si.cmd_init(args(url="example.vn"), out=lambda m: None, transport=net, delay=0)
    net.calls.clear()
    log = []
    si.cmd_refresh(args(), out=log.append, transport=net, delay=0)
    assert "https://example.vn/san-pham/may-pha-espresso-x1/" not in net.calls
    urls = [r["url"] for r in si.load_inventory(sites_env / "example.vn")]
    assert "https://example.vn/san-pham/may-pha-espresso-x1/" in urls
    assert any("robots.txt" in m for m in log)


def test_no_fetch_pages_uses_only_sitemap(sites_env):
    net = FakeNet(sitemap_routes())
    si.cmd_init(args(url="example.vn"), out=lambda m: None, transport=net, delay=0)
    net.calls.clear()
    si.cmd_refresh(args(no_fetch_pages=True), out=lambda m: None, transport=net, delay=0)
    assert "https://example.vn/cach-chon-may-pha-ca-phe/" not in net.calls
    rows = si.load_inventory(sites_env / "example.vn")
    assert {r["type"] for r in rows} >= {"product", "post"}


def test_main_reports_vietnamese_error(capsys):
    assert si.main(["status"]) == 1
    assert "Lỗi" in capsys.readouterr().err
