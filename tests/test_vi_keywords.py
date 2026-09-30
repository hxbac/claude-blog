"""Phase L: scripts/vi_keywords.py. No network; the wrapper call is mocked."""

from __future__ import annotations

import json

import pytest

import vi_keywords as vk


@pytest.fixture(autouse=True)
def _no_real_wrapper(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("real wrapper must not be called in tests")

    monkeypatch.setattr(vk, "_run_labs", boom)


def _keys(rows):
    return [r["keyword"] for r in rows]


def test_diacritic_and_ascii_forms():
    rows = vk.build_variants("mỹ phẩm")
    assert _keys(rows)[:2] == ["mỹ phẩm", "my pham"]
    assert rows[1]["form"] == vk.FORM_ASCII


def test_ascii_seed_does_not_invent_accents():
    rows = vk.build_variants("my pham")
    assert _keys(rows)[0] == "my pham"
    assert "mỹ phẩm" not in _keys(rows)


def test_regional_pairs_both_directions():
    assert "ly thủy tinh" in _keys(vk.build_variants("cốc thủy tinh"))
    assert "cốc thủy tinh" in _keys(vk.build_variants("ly thủy tinh"))
    pine = _keys(vk.build_variants("dứa"))
    assert "thơm" in pine and "khóm" in pine


def test_regional_uses_word_boundaries():
    # "ba lô" must not be treated as a regional word; "lợn" must not match "lợn cợn".
    assert vk.regional_variants("balo") == []
    assert vk.regional_variants("mỹ phẩm") == []


def test_intent_variants_present():
    keys = _keys(vk.build_variants("máy lọc nước"))
    for expected in ("máy lọc nước là gì", "giá máy lọc nước", "review máy lọc nước",
                     "máy lọc nước có tốt không", "nên mua máy lọc nước",
                     "top 10 máy lọc nước", "so sánh máy lọc nước", "máy lọc nước ở đâu"):
        assert expected in keys


def test_no_duplicates():
    keys = _keys(vk.build_variants("heo"))
    assert len(keys) == len(set(keys))


def test_no_key_degrades_gracefully(monkeypatch, capsys):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: False)
    assert vk.main(["mỹ phẩm"]) == 0
    out = capsys.readouterr().out
    assert "Chưa có khoá DataForSEO" in out
    assert "n/a" in out and "my pham" in out


def test_json_format_no_key(monkeypatch, capsys):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: False)
    vk.main(["mỹ phẩm", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["volumes_status"] == "unavailable"
    assert data["location_code"] == 2704 and data["language_code"] == "vi"
    assert all(r["volume"] == "n/a" for r in data["keywords"])


def test_volumes_merged_and_sorted(monkeypatch):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: True)
    seen = {}

    def fake(keywords, limit):
        seen["kw"], seen["limit"] = keywords, limit
        return {"status": "success", "keywords": [
            {"keyword": "mỹ phẩm", "search_volume": 5000},
            {"keyword": "my pham", "search_volume": 900},
            {"keyword": "giá mỹ phẩm", "search_volume": None},
        ]}

    monkeypatch.setattr(vk, "_run_labs", fake)
    res = vk.research("mỹ phẩm", limit=10)
    vols = {r["keyword"]: r["volume"] for r in res["keywords"]}
    assert vols["mỹ phẩm"] == 5000 and vols["my pham"] == 900
    assert vols["giá mỹ phẩm"] == "-"
    assert res["keywords"][0]["keyword"] == "mỹ phẩm"
    assert res["volumes_status"] == "ok"
    assert len(seen["kw"]) == 10 and seen["limit"] == 10


def test_limit_caps_request_and_marks_rest_na(monkeypatch):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: True)
    sent = {}
    monkeypatch.setattr(vk, "_run_labs", lambda kws, lim: sent.update(n=len(kws)) or
                        {"keywords": [{"keyword": kws[0], "search_volume": 10}]})
    res = vk.research("mỹ phẩm", limit=3)
    assert sent["n"] == 3
    assert sum(1 for r in res["keywords"] if r["volume"] == "n/a") == len(res["keywords"]) - 3
    assert "--limit" in res["note"]


def test_limit_hard_ceiling(monkeypatch):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: True)
    sent = {}
    monkeypatch.setattr(vk, "_run_labs", lambda kws, lim: sent.update(n=len(kws), lim=lim) or {"keywords": []})
    vk.research("mỹ phẩm", limit=10_000)
    assert sent["lim"] == vk.MAX_LIMIT and sent["n"] <= vk.MAX_LIMIT


@pytest.mark.parametrize("err,frag", [
    ("missing_credentials", "Chưa có khoá"),
    ("all_slots_failed", "Tất cả khoá DataForSEO"),
    ("api_error", "DataForSEO báo lỗi"),
])
def test_wrapper_errors_degrade(monkeypatch, err, frag):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: True)
    monkeypatch.setattr(vk, "_run_labs", lambda kws, lim: {"error": err, "message": "x"})
    res = vk.research("mỹ phẩm")
    assert frag in res["note"]
    assert all(r["volume"] == "n/a" for r in res["keywords"])


def test_markdown_table_shape(monkeypatch):
    monkeypatch.setattr(vk, "has_dataforseo_key", lambda: False)
    md = vk.render_markdown(vk.research("cốc"))
    assert "| Từ khoá | Dạng |" in md and "| ly |" in md


def test_no_volumes_flag_never_calls_wrapper(capsys):
    assert vk.main(["mỹ phẩm", "--no-volumes"]) == 0
    assert "n/a" in capsys.readouterr().out
