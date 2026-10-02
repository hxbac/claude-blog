"""Phase U-blog: Search Console in the writing pipeline. No network: the
blog-google subprocess is replaced by a fake runner or a fake subprocess.run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import content_decay as cd  # noqa: E402
import internal_links as il  # noqa: E402
import site_inventory as si  # noqa: E402

PROP = "sc-domain:example.vn"
HEADER = si.COLUMNS


def write_site(root: Path, rows: list, toml_extra: str = "") -> Path:
    d = root / "example.vn"
    d.mkdir(parents=True)
    (d / "site.toml").write_text(
        'base_url = "https://example.vn"\ncms = "other"\nbrand = "Example"\nlang = "vi"\n'
        f"sitemaps = []\ninclude = []\nexclude = []\n{toml_extra}", encoding="utf-8")
    full = []
    for r in rows:
        row = si.blank_row()
        row.update(r)
        full.append(row)
    si.write_csv_rows(d / "inventory.csv", full)
    return d


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    root = tmp_path / "sites"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_BLOG_SITES_ROOT", str(root))
    monkeypatch.delenv("GSC_PROPERTY", raising=False)
    return root


def args(**kw):
    base = dict(site=None, days=90, include_subdomains=False, top=20, min_impressions=5,
                json=False, urls=[], recent=0)
    base.update(kw)
    return argparse.Namespace(**base)


def runner_for(page_rows, query_rows):
    calls = []

    def run(script, a):
        calls.append((script, list(map(str, a))))
        dims = a[a.index("--dimensions") + 1]
        return {"rows": page_rows if dims == "page" else query_rows}

    run.calls = calls
    return run


PAGE_ROWS = [
    {"keys": ["https://www.example.vn/bai-a/"], "clicks": 3, "impressions": 100, "position": 8.0},
    {"keys": ["http://example.vn/bai-a"], "clicks": 1, "impressions": 100, "position": 12.0},
    {"keys": ["https://example.vn/moi"], "clicks": 0, "impressions": 4, "position": 30.0},
    {"keys": ["https://app.example.vn/"], "clicks": 9, "impressions": 50, "position": 2.0},
]
QUERY_ROWS = [
    {"keys": ["https://example.vn/bai-a", "may pha ca phe"], "clicks": 3, "impressions": 80, "position": 7.0},
    {"keys": ["https://example.vn/bai-a/", "ca phe"], "clicks": 1, "impressions": 90, "position": 15.0},
    {"keys": ["https://example.vn/moi", "bai moi"], "clicks": 0, "impressions": 4, "position": 30.0},
]


# ---- URL normalisation and scope ---------------------------------------------

@pytest.mark.parametrize("url", [
    "https://example.vn/bai-a", "http://example.vn/bai-a/", "https://www.example.vn/bai-a/",
    "HTTP://WWW.Example.vn/bai-a?utm_source=x#top",
])
def test_gsc_key_ignores_scheme_www_slash_tracking(url):
    assert si.gsc_key(url) == "https://example.vn/bai-a"


def test_gsc_key_decodes_percent_escapes_and_keeps_root():
    assert si.gsc_key("https://example.vn/b%C3%A0i-vi%E1%BA%BFt") == si.gsc_key("https://example.vn/bài-viết")
    assert si.gsc_key("http://www.example.vn") == "https://example.vn/"


def test_domain_property_covers_subdomains_url_prefix_does_not():
    assert si.property_covers("sc-domain:example.vn", "app.example.vn")
    assert si.property_covers("sc-domain:example.vn", "www.example.vn")
    assert not si.property_covers("sc-domain:example.vn", "other.vn")
    assert si.property_covers("https://www.example.vn/", "example.vn")
    assert not si.property_covers("https://example.vn/", "app.example.vn")


def test_subdomain_pages_are_not_part_of_the_site_by_default():
    pages, skipped = si.aggregate_gsc(PAGE_ROWS, QUERY_ROWS, "example.vn")
    assert "https://app.example.vn/" not in pages and skipped == {"app.example.vn": 1}
    pages, skipped = si.aggregate_gsc(PAGE_ROWS, QUERY_ROWS, "example.vn", include_subdomains=True)
    assert "https://app.example.vn/" in pages and not skipped


def test_aggregate_merges_url_variants_weighted_by_impressions():
    pages, _ = si.aggregate_gsc(PAGE_ROWS, QUERY_ROWS, "example.vn")
    a = pages["https://example.vn/bai-a"]
    assert (a["clicks"], a["impressions"], a["position"]) == (4, 200, 10.0)
    assert a["top_query"] == "may pha ca phe"     # most clicks beats most impressions


# ---- property resolution -----------------------------------------------------

def test_property_from_site_toml_beats_env(monkeypatch):
    monkeypatch.setenv("GSC_PROPERTY", "sc-domain:other.vn")
    assert si.gsc_property_for({"base_url": "https://example.vn", "gsc_property": PROP}) == PROP


def test_env_property_used_only_when_host_matches(monkeypatch):
    cfg = {"base_url": "https://www.example.vn"}
    monkeypatch.setenv("GSC_PROPERTY", PROP)
    assert si.gsc_property_for(cfg) == PROP
    monkeypatch.setenv("GSC_PROPERTY", "sc-domain:other.vn")
    assert si.gsc_property_for(cfg) == ""
    with pytest.raises(si.InventoryError, match="không bao gồm"):
        si.require_property(cfg)


def test_missing_property_is_a_vietnamese_error():
    with pytest.raises(si.InventoryError, match="Chưa kết nối được Search Console"):
        si.require_property({"base_url": "https://example.vn"})


# ---- gsc-sync ---------------------------------------------------------------

EDITED = {"url": "https://example.vn/bai-a", "type": "post", "title": "Bài A", "source": "sitemap",
          "focus_keyword": "máy pha cà phê", "anchors": "cách pha|máy pha", "priority": "4",
          "exclude": "", "notes": "đừng đụng", "gsc_clicks": "99", "gsc_top_query": "cũ"}
UNSEEN = {"url": "https://example.vn/chua-co-so-lieu", "type": "post", "title": "Chưa có", "notes": "n"}


def read_rows(d: Path) -> dict:
    return {r["url"]: r for r in si.load_inventory(d)}


def test_sync_fills_gsc_columns_adds_gsc_rows_and_keeps_editable(env):
    d = write_site(env, [EDITED, UNSEEN], f'gsc_property = "{PROP}"\n')
    out = []
    assert si.cmd_gsc_sync(args(), out=out.append, runner=runner_for(PAGE_ROWS, QUERY_ROWS)) == 0
    rows = read_rows(d)
    a = rows["https://example.vn/bai-a"]
    assert (a["gsc_clicks"], a["gsc_impressions"], a["gsc_position"], a["gsc_top_query"]) == (
        "4", "200", "10", "may pha ca phe")
    assert a["gsc_synced_at"]
    for col in si.EDITABLE:
        assert a[col] == EDITED[col]
    u = rows["https://example.vn/chua-co-so-lieu"]
    assert (u["gsc_clicks"], u["gsc_impressions"], u["gsc_position"], u["gsc_top_query"]) == ("0", "0", "", "")
    assert u["notes"] == "n"
    new = rows["https://example.vn/moi"]
    assert new["source"] == "gsc" and new["gsc_impressions"] == "4"
    assert "https://app.example.vn/" not in rows
    text = "\n".join(out)
    assert "app.example.vn" in text and "--include-subdomains" in text


def test_resync_overwrites_only_gsc_columns(env):
    d = write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    si.cmd_gsc_sync(args(), out=lambda s: None, runner=runner_for(PAGE_ROWS, QUERY_ROWS))
    first = read_rows(d)["https://example.vn/bai-a"]
    # the marketer edits between syncs, GSC numbers change
    rows = si.load_inventory(d)
    for r in rows:
        if r["url"].endswith("bai-a"):
            r["notes"] = "sửa tay lần hai"
            r["priority"] = "5"
    si.write_csv_rows(d / "inventory.csv", rows)
    newer = [{"keys": ["https://example.vn/bai-a"], "clicks": 10, "impressions": 20, "position": 3.0}]
    si.cmd_gsc_sync(args(), out=lambda s: None,
                    runner=runner_for(newer, [{"keys": ["https://example.vn/bai-a", "q mới"],
                                               "clicks": 2, "impressions": 5, "position": 3}]))
    second = read_rows(d)["https://example.vn/bai-a"]
    assert second["notes"] == "sửa tay lần hai" and second["priority"] == "5"
    assert second["gsc_clicks"] == "10" and second["gsc_top_query"] == "q mới"
    assert first["gsc_clicks"] == "4"
    # the page that vanished from GSC keeps its row, numbers reset to zero
    assert read_rows(d)["https://example.vn/moi"]["gsc_impressions"] == "0"


def test_sync_include_subdomains_adds_them(env):
    d = write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    si.cmd_gsc_sync(args(include_subdomains=True), out=lambda s: None, runner=runner_for(PAGE_ROWS, QUERY_ROWS))
    assert "https://app.example.vn/" in read_rows(d)


def test_gsc_rows_survive_a_refresh_merge():
    gsc_row = dict(si.blank_row(), url="https://example.vn/moi", type="page", source="gsc")
    merged = si.merge_inventory([gsc_row], [], complete=True)
    assert merged[0]["type"] == "page"          # not marked gone


def test_sync_failure_leaves_inventory_untouched(env):
    d = write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    before = (d / "inventory.csv").read_bytes()

    def boom(script, a):
        raise si.InventoryError("Search Console không trả lời sau 240 giây.")

    with pytest.raises(si.InventoryError, match="không trả lời"):
        si.cmd_gsc_sync(args(), out=lambda s: None, runner=boom)
    assert (d / "inventory.csv").read_bytes() == before
    with pytest.raises(si.InventoryError):
        si.cmd_gsc_sync(args(), out=lambda s: None, runner=None)   # real runner, no env: not reached either
    assert (d / "inventory.csv").read_bytes() == before


def test_sync_without_property_changes_nothing(env):
    d = write_site(env, [EDITED])
    before = (d / "inventory.csv").read_bytes()
    with pytest.raises(si.InventoryError, match="Chưa kết nối được Search Console"):
        si.cmd_gsc_sync(args())
    assert (d / "inventory.csv").read_bytes() == before


# ---- the subprocess seam -------------------------------------------------------

class Done:
    def __init__(self, out="", err="", code=0):
        self.stdout, self.stderr, self.returncode = out, err, code


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    runner = tmp_path / "run.py"
    runner.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_BLOG_GSC_RUNNER", str(runner))
    calls = []

    def install(result):
        def run(cmd, **kw):
            calls.append((cmd, kw))
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(si.subprocess, "run", run)
        return calls
    return install


def test_subprocess_gets_timeout_and_parses_json_after_setup_noise(fake_run):
    calls = fake_run(Done('First-time setup...\nEnvironment ready!\n{"rows": [{"keys": ["x"]}], "error": null}\n'))
    data = si.run_google_script("gsc_query", ["--property", PROP])
    assert data["rows"][0]["keys"] == ["x"]
    cmd, kw = calls[0]
    assert kw["timeout"] == si.GSC_TIMEOUT and cmd[-1] == "--json" and "gsc_query" in cmd


def test_subprocess_timeout_is_vietnamese(fake_run):
    fake_run(subprocess.TimeoutExpired("run.py", 240))
    with pytest.raises(si.InventoryError, match="không trả lời sau"):
        si.run_google_script("gsc_query", [])


@pytest.mark.parametrize("payload,needle", [
    ('{"rows": [], "error": "Could not build GSC service. Check service account credentials."}', "Chưa kết nối"),
    ('{"rows": [], "error": "Permission denied for property"}', "từ chối quyền"),
    ('{"rows": [], "error": "Property \'x\' not found."}', "không thấy property"),
    ('{"rows": [], "error": "GSC API error: boom"}', "Search Console báo lỗi"),
])
def test_subprocess_errors_are_vietnamese(fake_run, payload, needle):
    fake_run(Done(payload))
    with pytest.raises(si.InventoryError, match=needle):
        si.run_google_script("gsc_query", [])


def test_subprocess_garbage_output_is_not_a_traceback(fake_run):
    fake_run(Done("", "Traceback...\nImportError: no module", 1))
    with pytest.raises(si.InventoryError, match="Danh sách web được giữ nguyên"):
        si.run_google_script("gsc_query", [])


def test_missing_runner_is_vietnamese(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_BLOG_GSC_RUNNER", str(tmp_path / "nope.py"))
    monkeypatch.setattr(si.Path, "is_file", lambda self: False)
    with pytest.raises(si.InventoryError, match="Không thấy skill blog-google"):
        si.gsc_runner()


# ---- opportunities --------------------------------------------------------------

OPP_ROWS = [
    {"keys": ["https://example.vn/bai-a", "máy pha cà phê"], "clicks": 1, "impressions": 90, "position": 7.2},
    {"keys": ["https://example.vn/bai-a", "cách rửa xe máy"], "clicks": 0, "impressions": 40, "position": 14.0},
    {"keys": ["https://example.vn/bai-a", "xay cà phê"], "clicks": 0, "impressions": 30, "position": 3.0},
    {"keys": ["https://example.vn/bai-a", "ít hiển thị"], "clicks": 0, "impressions": 2, "position": 9.0},
    {"keys": ["https://example.vn/bai-a", "quá xa"], "clicks": 0, "impressions": 60, "position": 40.0},
    {"keys": ["https://app.example.vn/", "tên miền phụ"], "clicks": 0, "impressions": 80, "position": 9.0},
]


def test_opportunities_only_real_rows_in_range_and_grounded_action(env):
    d = write_site(env, [dict(EDITED, title="Máy pha cà phê tại nhà", gsc_clicks="")])
    rows = si.load_inventory(d)
    res = si.find_opportunities(rows, OPP_ROWS, "example.vn")
    queries = [i["query"] for i in res["items"]]
    assert queries == ["máy pha cà phê", "cách rửa xe máy"]       # sorted by impressions; nothing invented
    assert res["items"][0]["action"].startswith("Thêm link nội bộ")        # on topic, position 5 to 10
    assert res["items"][1]["action"].startswith("Viết bài mới")            # off topic
    assert all(i["position"] >= 5 and i["position"] <= 20 for i in res["items"])


def test_opportunity_between_11_and_20_asks_for_a_refresh(env):
    d = write_site(env, [dict(EDITED, title="Máy pha cà phê tại nhà")])
    row = si.load_inventory(d)[0]
    assert si.opportunity_action(15.0, row, "máy pha cà phê").startswith("Làm mới bài")


def test_opportunities_empty_says_so_without_inventing(env):
    write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    out = []
    si.cmd_opportunities(args(), out=out.append, runner=runner_for([], []))
    assert "Chưa có từ khoá nào ở vị trí 5 đến 20" in out[0] and "không tự bịa" in out[0]


def test_opportunities_command_prints_table(env):
    write_site(env, [dict(EDITED, title="Máy pha cà phê tại nhà")], f'gsc_property = "{PROP}"\n')
    out = []
    si.cmd_opportunities(args(), out=out.append, runner=runner_for([], OPP_ROWS))
    assert "| máy pha cà phê | 7.2 | 90 | 1 | https://example.vn/bai-a |" in out[0]
    assert "tên miền phụ" not in out[0]


# ---- index-check -------------------------------------------------------------------

INSPECT_OK = {"url": "https://example.vn/bai-a", "verdict": "PASS",
              "index_status": {"coverage_state": "Submitted and indexed", "last_crawl_time": "2026-10-01T23:28:44Z"},
              "canonical": {"google_canonical": "https://example.vn/bai-a", "user_canonical": "https://example.vn/bai-a"}}


def test_explain_inspection_verdicts():
    ok = si.explain_inspection(INSPECT_OK)
    assert ok["ok"] and ok["text"].startswith("Đã được Google lập chỉ mục") and "2026-10-01 23:28" in ok["text"]
    neutral = si.explain_inspection(dict(INSPECT_OK, verdict="NEUTRAL"))
    assert "Chưa được Google lập chỉ mục" in neutral["text"] and not neutral["ok"]
    mismatch = si.explain_inspection(dict(INSPECT_OK, canonical={"google_canonical": "https://example.vn/x",
                                                                 "user_canonical": "https://example.vn/y"}))
    assert "khác nhau" in mismatch["text"]
    assert si.explain_inspection({"url": "u", "error": "boom"})["text"].startswith("Không kiểm tra được")


def test_index_check_is_read_only_and_checks_scope(env):
    write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    calls = []

    def run(script, a):
        calls.append((script, a))
        return INSPECT_OK

    out = []
    si.cmd_index_check(args(urls=["https://example.vn/bai-a", "https://other.vn/x", "bai-a"]),
                       out=out.append, runner=run, sleep=lambda s: None)
    assert [c[0] for c in calls] == ["gsc_inspect"]           # never indexing_notify
    text = "\n".join(out)
    assert "Đã được Google lập chỉ mục" in text and "nằm ngoài property" in text
    assert "không gửi hay yêu cầu lập chỉ mục" in text


def test_index_check_recent_takes_newest_posts(env):
    write_site(env, [
        {"url": "https://example.vn/cu", "type": "post", "lastmod": "2025-01-01"},
        {"url": "https://example.vn/moi", "type": "post", "lastmod": "2026-09-30"},
        {"url": "https://example.vn/trang", "type": "page", "lastmod": "2026-10-01"},
        {"url": "https://example.vn/loai", "type": "post", "lastmod": "2026-10-01", "exclude": "yes"},
    ], f'gsc_property = "{PROP}"\n')
    seen = []
    si.cmd_index_check(args(recent=2), out=lambda s: None,
                       runner=lambda script, a: seen.append(a[0]) or INSPECT_OK, sleep=lambda s: None)
    assert seen == ["https://example.vn/moi", "https://example.vn/cu"]


def test_index_check_needs_a_url(env):
    write_site(env, [EDITED], f'gsc_property = "{PROP}"\n')
    with pytest.raises(si.InventoryError, match="ít nhất một địa chỉ"):
        si.cmd_index_check(args())


def test_parser_has_the_new_subcommands():
    p = si.build_parser()
    assert p.parse_args(["gsc-sync", "--days", "30"]).days == 30
    assert p.parse_args(["opportunities"]).min_impressions == si.OPP_MIN_IMPRESSIONS
    assert p.parse_args(["index-check", "https://a.vn/", "--recent", "3"]).recent == 3


# ---- internal_links: striking distance ------------------------------------------------

def il_site(env, rows):
    d = write_site(env, rows)
    return il.load_site(d)


POST = {"url": "https://example.vn/may-pha-ca-phe", "type": "post", "title": "Cách chọn máy pha cà phê",
        "focus_keyword": "máy pha cà phê"}


def test_no_gsc_data_means_boost_one():
    assert il.striking_boost(POST) == 1.0
    assert il.striking_boost(dict(POST, gsc_position="8", gsc_impressions="3")) == 1.0   # under the floor
    assert il.striking_boost(dict(POST, gsc_position="3", gsc_impressions="500")) == 1.0  # already top
    assert il.striking_boost(dict(POST, gsc_position="30", gsc_impressions="500")) == 1.0
    assert il.striking_boost(dict(POST, gsc_position="x", gsc_impressions="500")) == 1.0


def test_striking_boost_is_documented_multiplier_and_capped_by_priority_five():
    striking = dict(POST, gsc_position="8.4", gsc_impressions="120")
    assert il.STRIKING_BOOST == 1.25
    assert il.striking_boost(striking) == 1.25
    assert il.striking_boost(dict(striking, priority="4")) == pytest.approx((5 / 3) / (4 / 3))  # capped at 1.25
    assert il.striking_boost(dict(striking, priority="5")) == 1.0                                # already the ceiling
    for p in "12345":
        row = dict(striking, priority=p)
        assert il._priority(row) * il.striking_boost(row) <= 5 / 3 + 1e-9


def test_candidates_identical_without_gsc_and_boosted_with_it(env, tmp_path):
    other = {"url": "https://example.vn/may-xay", "type": "post", "title": "Máy xay cà phê tại nhà",
             "focus_keyword": "máy xay cà phê"}
    base = il.candidates(il_site(env, [POST, other]), "máy cà phê")
    assert all("striking" not in c for c in base["candidates"])
    root2 = tmp_path / "sites2"
    root2.mkdir()
    boosted = [dict(POST, gsc_position="9", gsc_impressions="100", gsc_clicks="1"), other]
    res = il.candidates(il.load_site(write_site(root2, boosted)), "máy cà phê")
    one = next(c for c in res["candidates"] if c["url"] == POST["url"])
    ref = next(c for c in base["candidates"] if c["url"] == POST["url"])
    assert one["striking"] and one["score"] == pytest.approx(ref["score"] * 1.25, rel=1e-3)
    assert "sắp lên top" in il.render_candidates(res)


FM = "---\ntitle: Bài thử\nslug: bai-thu\ncanonical: https://example.vn/bai-thu\nlang: vi\n---\n"


def find_for(site, body, tmp_path):
    path = tmp_path / "d.md"
    path.write_text(FM + body, encoding="utf-8")
    return il.find_candidates(il.load_draft(path), site)


def test_gsc_top_query_becomes_an_anchor_only_where_spelled_out(env, tmp_path):
    row = {"url": "https://example.vn/x", "type": "post", "title": "Mở quán nhỏ",
           "description": "Cà phê sữa đá cho quán nhỏ", "gsc_top_query": "cà phê sữa đá"}
    site = il_site(env, [row])
    forms = il.RowForms(site.rows[0], site)
    assert forms.gsc == ("ca", "phe", "sua", "da") and forms.match(("ca", "phe", "sua", "da")) == "gsc"
    spelled = find_for(site, "\n# Bài thử\n\nMùa hè quán nhỏ nào cũng bán cà phê sữa đá cho khách.\n", tmp_path)
    assert [c.span.text for c in spelled] == ["cà phê sữa đá"] and spelled[0].anchor_type == "partial"
    # same words, marks stripped: Google's query is not there verbatim, so no gsc anchor
    plain = find_for(site, "\n# Bài thử\n\nMua he quán nhỏ nào cũng bán ca phe sua da cho khach.\n", tmp_path)
    assert not any(c.span.words == forms.gsc for c in plain)
    # without the column the same paragraph gives no such anchor
    (tmp_path / "s2").mkdir()
    site2 = il.load_site(write_site(tmp_path / "s2", [dict(row, gsc_top_query="")]))
    none = find_for(site2, "\n# Bài thử\n\nMùa hè quán nhỏ nào cũng bán cà phê sữa đá cho khách.\n", tmp_path)
    assert not any(c.span.words == forms.gsc for c in none)


def test_a_row_without_gsc_query_gets_no_gsc_form(env):
    site = il_site(env, [POST])
    assert il.RowForms(site.rows[0], site).gsc == ()


# ---- content_decay: short history -------------------------------------------------------

def test_short_history_message_names_the_first_date_and_the_ready_date():
    msg = cd.short_history_message("2026-08-05", today=date(2026, 8, 20))
    assert "từ ngày 2026-08-05" in msg and "2026-09-30" in msg and "56 ngày" in msg
    late = cd.short_history_message("2026-08-05", today=date(2026, 10, 2))
    assert "2026-09-30" not in late and "vẫn không có lượt hiển thị" in late
    assert "error" not in msg.lower()
    assert "chưa có dữ liệu cho kỳ trước" in cd.short_history_message(None)


def test_cli_empty_previous_explains_instead_of_failing(tmp_path, capsys):
    cur = tmp_path / "c.json"
    prev = tmp_path / "p.json"
    cur.write_text(json.dumps([{"page": "https://a.vn/", "clicks": 3, "impressions": 20}]), encoding="utf-8")
    prev.write_text("[]", encoding="utf-8")
    assert cd.main([str(cur), str(prev), "--first-data-date", "2026-08-05"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "short_history" and payload["first_data_date"] == "2026-08-05"
    assert "contains no rows" not in json.dumps(payload)
    assert cd.main([str(cur), str(prev), "--format", "markdown"]) == 0
    assert "chưa có kỳ trước để so sánh" in capsys.readouterr().out


def fake_live(monkeypatch, by_dim_range):
    calls = []

    def live(prop, dims, start, end):
        calls.append((dims, start, end))
        return by_dim_range(dims, start, end)

    monkeypatch.setattr(cd, "live_rows", live)
    return calls


def test_live_falls_back_to_28_against_28_when_both_have_rows(monkeypatch):
    today = date(2026, 10, 2)                       # end = 2026-09-29

    def rows(dims, start, end):
        if dims == "date":
            return [{"keys": ["2026-08-05"]}, {"keys": ["2026-09-01"]}]
        if start >= "2026-08-05":                   # both 28-day windows are inside the data
            clicks = 1 if end < "2026-09-02" else 0
            return [{"keys": ["https://a.vn/"], "page": "https://a.vn/", "clicks": 10 if clicks else 2, "impressions": 100}]
        return []                                   # the 90-day previous period is empty

    fake_live(monkeypatch, rows)
    rep = cd.analyze_live(PROP, 90, 0.2, "clicks", today=today)
    assert rep["status"] == "ok" and rep["period_days"] == 28 and rep["first_data_date"] == "2026-08-05"
    assert "Chưa đủ lịch sử cho 90 ngày" in rep["message"] and "quá ít để kết luận" in rep["message"]
    assert rep["current_range"] == ["2026-09-02", "2026-09-29"]
    assert rep["decays"][0]["page"] == "https://a.vn/"


def test_live_with_no_previous_rows_gives_the_vietnamese_report(monkeypatch):
    def rows(dims, start, end):
        if dims == "date":
            return [{"keys": ["2026-09-20"]}]
        return [{"keys": ["https://a.vn/"], "page": "https://a.vn/", "clicks": 1, "impressions": 9}] if start >= "2026-09-01" else []

    fake_live(monkeypatch, rows)
    rep = cd.analyze_live(PROP, 90, 0.2, "clicks", today=date(2026, 10, 2))
    assert rep["status"] == "short_history" and rep["first_data_date"] == "2026-09-20"
    assert rep["current_pages"] == 1 and "từ ngày 2026-09-20" in rep["message"]


def test_live_uses_the_full_period_when_history_is_long_enough(monkeypatch):
    fake_live(monkeypatch, lambda dims, s, e: [{"keys": ["2025-01-01"]}] if dims == "date" else
              [{"keys": ["https://a.vn/"], "page": "https://a.vn/", "clicks": 100, "impressions": 900}])
    rep = cd.analyze_live(PROP, 90, 0.2, "clicks", today=date(2026, 10, 2))
    assert rep["period_days"] == 90 and not rep.get("message")
