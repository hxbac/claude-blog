#!/usr/bin/env python3
"""Vietnamese keyword variants with Vietnam search volumes.

Given a seed keyword, emit the diacritic and non-diacritic forms, Bac/Nam
synonym variants from a small curated table, and intent-modifier variants,
then look up monthly volumes at location 2704 (Vietnam, language vi) through
``dataforseo_labs.py search-volume`` (the rotating-key wrapper) and merge
everything into one table.

Works without a DataForSEO key: the variant list is still produced, volumes
read "n/a" and a one-line Vietnamese note says the key is missing. Keys are
never read into this module's output.

Usage:
    python3 vi_keywords.py "mỹ phẩm"
    python3 vi_keywords.py "mỹ phẩm" --format json --limit 30
    python3 vi_keywords.py "mỹ phẩm" --no-volumes      # offline, no API call

Cost: one live keyword_overview request, about $0.01 plus $0.0001 per
keyword. --limit (default 40, hard ceiling 200) caps how many variants are
ever sent.

Non-diacritic to diacritic is not reversible in general (ma = ma, mã, má,
mả, mạ, mà), so a seed typed without accents only yields itself plus the
regional and intent variants; type the seed with accents for both forms.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import env_file  # noqa: E402
from vi_text import normalize, to_ascii  # noqa: E402

LOCATION_VN = 2704
LANGUAGE_VN = "vi"
DEFAULT_LIMIT = 40
MAX_LIMIT = 200  # mirrors dataforseo_labs.SEARCH_VOLUME_MAX_KEYWORDS

# Well-known Bac/Nam (and Bac/Trung) vocabulary pairs only. Each tuple is a
# set of interchangeable words for the same thing. Do not add a pair unless a
# northern and a southern speaker would both recognise it without hesitation.
REGIONAL_GROUPS: tuple[tuple[str, ...], ...] = (
    ("lợn", "heo"),
    ("ly", "cốc"),
    ("thìa", "muỗng"),
    ("ngô", "bắp"),
    ("bát", "chén"),
    ("mũ", "nón"),
    ("dứa", "thơm", "khóm"),
    ("lạc", "đậu phộng"),
    ("vừng", "mè"),
    ("quả", "trái"),
    ("ô tô", "xe hơi"),
    ("điều hòa", "máy lạnh"),
    ("xà phòng", "xà bông"),
    # Not ("túi", "bịch"): in the South "bịch" is a plastic or snack bag, never a
    # handbag or backpack, so the swap produced "bịch đeo chéo" for shop data.
    ("kính", "kiếng"),
    ("dù", "ô"),
)

# (modifier, position). "prefix" puts it before the seed, "suffix" after.
INTENT_MODIFIERS: tuple[tuple[str, str], ...] = (
    ("là gì", "suffix"),
    ("cách", "prefix"),
    ("giá", "prefix"),
    ("review", "prefix"),
    ("có tốt không", "suffix"),
    ("nên mua", "prefix"),
    ("top 10", "prefix"),
    ("so sánh", "prefix"),
    ("ở đâu", "suffix"),
)

NO_KEY_NOTE = (
    "Chưa có khoá DataForSEO nên khối lượng tìm kiếm ghi n/a; "
    "xem docs/CREDENTIALS.md để thêm khoá."
)

FORM_ORIGINAL = "gốc"
FORM_ASCII = "không dấu"
FORM_REGIONAL = "Bắc/Nam"
FORM_INTENT = "ý định"


def _has_diacritics(text: str) -> bool:
    return to_ascii(text) != text


def _key(text: str) -> str:
    return " ".join(normalize(text).lower().split())


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return f" {phrase} " in f" {haystack} "


def _replace_phrase(haystack: str, old: str, new: str) -> str:
    return f" {haystack} ".replace(f" {old} ", f" {new} ").strip()


def regional_variants(seed: str) -> list[tuple[str, str]]:
    """Return (variant, note) pairs with one regional word swapped."""
    seed_key = _key(seed)
    seed_ascii = to_ascii(seed_key)
    accented = _has_diacritics(seed_key)
    found: list[tuple[str, str]] = []
    for group in REGIONAL_GROUPS:
        for word in group:
            probe = word if accented else to_ascii(word)
            text = seed_key if accented else seed_ascii
            if not _contains_phrase(text, probe):
                continue
            for other in group:
                if other == word:
                    continue
                repl = other if accented else to_ascii(other)
                found.append((_replace_phrase(text, probe, repl), f"{word} / {other}"))
            break
    return found


def intent_variants(base: str) -> list[str]:
    out = []
    for modifier, position in INTENT_MODIFIERS:
        out.append(f"{base} {modifier}" if position == "suffix" else f"{modifier} {base}")
    return out


def build_variants(seed: str) -> list[dict]:
    """Ordered, de-duplicated variant rows: keyword, form, note."""
    rows: list[dict] = []
    seen: set[str] = set()

    def add(keyword: str, form: str, note: str = "") -> None:
        k = _key(keyword)
        if k and k not in seen:
            seen.add(k)
            rows.append({"keyword": k, "form": form, "note": note})

    base = _key(seed)
    add(base, FORM_ORIGINAL)
    if _has_diacritics(base):
        add(to_ascii(base), FORM_ASCII)

    regional = regional_variants(base)
    for variant, note in regional:
        add(variant, FORM_REGIONAL, note)
        if _has_diacritics(variant):
            add(to_ascii(variant), FORM_ASCII, f"{note} (không dấu)")

    for variant in intent_variants(base):
        add(variant, FORM_INTENT)
    if _has_diacritics(base):
        for variant in intent_variants(to_ascii(base)):
            add(variant, FORM_INTENT, "không dấu")
    for regional_kw, note in regional:
        for variant in intent_variants(regional_kw):
            add(variant, FORM_INTENT, note)
    return rows


def has_dataforseo_key() -> bool:
    try:
        env_file.load()
        return bool(env_file.slots("dataforseo"))
    except Exception:
        return False


def _run_labs(keywords: list[str], limit: int) -> dict:
    """Call dataforseo_labs.py search-volume; returns its parsed JSON.

    This is the single seam tests replace. stderr is inherited so that
    [keyring] rotation lines reach the user unchanged.
    """
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "dataforseo_labs.py"),
        "search-volume",
        *keywords,
        "--location", str(LOCATION_VN),
        "--language", LANGUAGE_VN,
        "--limit", str(limit),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=180)
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return {"error": "bad_output", "message": "dataforseo_labs.py returned no JSON."}


def fetch_volumes(keywords: list[str], limit: int) -> tuple[dict[str, int | None], str]:
    """Return ({keyword: volume}, note). note is empty on success."""
    if not has_dataforseo_key():
        return {}, NO_KEY_NOTE
    sent = keywords[:limit]
    resp = _run_labs(sent, limit)
    err = resp.get("error")
    if err == "missing_credentials":
        return {}, NO_KEY_NOTE
    if err == "all_slots_failed":
        return {}, (
            "Tất cả khoá DataForSEO đều bị từ chối, cần khoá mới hoặc nạp thêm "
            "tiền (xem docs/CREDENTIALS.md); khối lượng ghi n/a."
        )
    if err:
        return {}, f"DataForSEO báo lỗi ({err}) nên khối lượng ghi n/a."
    volumes: dict[str, int | None] = {}
    for item in resp.get("keywords") or []:
        volumes[_key(str(item.get("keyword", "")))] = item.get("search_volume")
    return volumes, ""


def _cost_note(count: int) -> str:
    return (
        f"Chi phí ước tính: 1 yêu cầu DataForSEO, khoảng ${0.01 + 0.0001 * count:.4f} "
        f"cho {count} từ khoá (giới hạn --limit, tối đa {MAX_LIMIT})."
    )


def research(seed: str, limit: int = DEFAULT_LIMIT, volumes: bool = True) -> dict:
    limit = max(1, min(limit, MAX_LIMIT))
    rows = build_variants(seed)
    sent = [r["keyword"] for r in rows][:limit]
    note = ""
    vols: dict[str, int | None] = {}
    if volumes:
        vols, note = fetch_volumes(sent, limit)
    else:
        note = "Bỏ qua tra khối lượng (--no-volumes); khối lượng ghi n/a."
    looked_up = bool(vols) or (volumes and not note)
    for row in rows:
        k = row["keyword"]
        if not looked_up or k not in sent:
            row["volume"] = "n/a"
        else:
            v = vols.get(k)
            row["volume"] = v if v is not None else "-"
    if looked_up:
        rows.sort(key=lambda r: (not isinstance(r["volume"], int),
                                 -(r["volume"] if isinstance(r["volume"], int) else 0)))
    skipped = max(0, len(rows) - limit)
    if looked_up and skipped and not note:
        note = f"{skipped} biến thể vượt giới hạn --limit nên chưa tra (ghi n/a)."
    return {
        "seed": seed,
        "location_code": LOCATION_VN,
        "language_code": LANGUAGE_VN,
        "volumes_status": "ok" if looked_up else "unavailable",
        "note": note,
        "cost_note": _cost_note(len(sent)) if volumes else "",
        "keywords": rows,
    }


def render_markdown(result: dict) -> str:
    lines = [f"# Từ khoá cho: {result['seed']}", ""]
    if result["note"]:
        lines += [f"> {result['note']}", ""]
    lines += ["| Từ khoá | Dạng | Ghi chú | Lượt tìm/tháng (VN) |", "| --- | --- | --- | --- |"]
    for r in result["keywords"]:
        lines.append(f"| {r['keyword']} | {r['form']} | {r['note']} | {r['volume']} |")
    if result["cost_note"]:
        lines += ["", result["cost_note"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("seed", nargs="+", help="Seed keyword, e.g. 'mỹ phẩm'")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Max keywords sent to DataForSEO (default {DEFAULT_LIMIT}, ceiling {MAX_LIMIT})")
    parser.add_argument("--no-volumes", action="store_true", help="Offline: variants only, no API call")
    args = parser.parse_args(argv)
    seed = unicodedata.normalize("NFC", " ".join(args.seed)).strip()
    if not seed:
        print("Cần một từ khoá gốc.", file=sys.stderr)
        return 2
    result = research(seed, limit=args.limit, volumes=not args.no_volumes)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
