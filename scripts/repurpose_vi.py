#!/usr/bin/env python3
"""Vietnamese repurpose scaffolds: Zalo OA, Facebook, TikTok.

A scaffold fixes the parts that must not vary inside one piece: the address
form (xưng hô) and the channel's structure. The writer fills the fields with
real content from the post. Every scaffold is built from one register table, so
a piece cannot start in `bạn` and end in `quý khách`.

Usage:
    python3 scripts/repurpose_vi.py render --channel facebook --register peer \\
        --title "..." --hook "..." --point "..." --point "..." --cta "..." --link URL
    python3 scripts/repurpose_vi.py check <file.md>   # register drift + AI tells

Registers: peer (bạn / mình), polite (anh chị), formal (quý khách).
Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vi_prose  # noqa: E402

#: register -> address forms. ``we`` is the writer's own reference; it is chosen
#: so it is never a marker of another register.
REGISTERS = {
    "peer": {"you": "bạn", "You": "Bạn", "we": "mình", "hello": "Chào bạn"},
    "polite": {"you": "anh chị", "You": "Anh chị", "we": "chúng tôi", "hello": "Chào anh chị"},
    "formal": {"you": "quý khách", "You": "Quý khách", "we": "chúng tôi", "hello": "Kính chào quý khách"},
}

CHANNELS = ("zalo_oa", "facebook", "tiktok")

_ZALO_OA = """\
# Zalo OA: {title}

Tiêu đề bài viết OA: {title}
Ảnh bìa: dùng ảnh hero của bài, tỷ lệ theo yêu cầu hiện hành của Zalo OA.

{hello},

{hook}

{points}

{You} có thể đọc bản đầy đủ tại đây: {link}

{cta}

Ghi chú biên tập (xóa trước khi gửi):
- Zalo OA đọc trên điện thoại: đoạn ngắn, mỗi đoạn một ý.
- Kiểm tra giới hạn ký tự và định dạng hiện hành của Zalo OA trước khi gửi; các số trong tài liệu này chỉ là mục tiêu biên tập.
- Giữ một cách xưng hô cho cả tin; dùng "{you}" từ đầu đến cuối.
"""

_FACEBOOK = """\
# Facebook: {title}

{hook}

{points}

{cta} Ý nào {you} thấy dùng được nhất? Cho {we} biết ở phần bình luận.

Liên kết bài đầy đủ: đặt trong bình luận đầu tiên hoặc cuối bài ({link}); thử cả hai và so sánh kết quả, đừng coi đây là quy tắc cố định.
Hashtag: {hashtags}

Ghi chú biên tập (xóa trước khi đăng):
- Hook nằm trong khoảng 125 ký tự đầu, vì người đọc chỉ thấy phần đó trước nút "Xem thêm".
- Mở bằng một tình huống cụ thể hoặc một con số có nguồn, không mở bằng câu hỏi chung chung.
- Tối đa hai biểu tượng cảm xúc, tối đa ba hashtag.
- Nếu mở bằng "{you}", giữ "{you}" đến hết bài.
"""

_TIKTOK = """\
# TikTok: {title}

Thời lượng mục tiêu: 30 đến 60 giây. Lời thoại đọc thành tiếng, nên câu ngắn.

## 0 đến 3 giây: hook
- Lời thoại: {hook}
- Chữ trên màn hình: rút gọn hook còn tối đa tám chữ.
- Hình: cận cảnh vấn đề hoặc kết quả, không mở bằng logo.

## Nội dung chính
{beats}

## Chốt
- Lời thoại: {cta}
- Chữ trên màn hình: {link}

## Chú thích video
{title}. {You} xem bản đầy đủ ở liên kết trong tiểu sử. {hashtags}

Ghi chú biên tập (xóa trước khi quay):
- Bật phụ đề tiếng Việt, vì nhiều người xem không bật tiếng.
- Xưng hô trong lời thoại và chú thích phải là "{you}" từ đầu đến cuối.
- Số liệu chỉ lấy từ bài gốc đã có nguồn.
"""

_TEMPLATES = {"zalo_oa": _ZALO_OA, "facebook": _FACEBOOK, "tiktok": _TIKTOK}


def render(channel: str, register: str, *, title: str, hook: str, points: list[str],
           cta: str, link: str = "[liên kết bài]", hashtags: Optional[list[str]] = None) -> str:
    """Return the scaffold for ``channel`` in ``register``, fields filled in."""
    if channel not in _TEMPLATES:
        raise ValueError(f"channel must be one of {CHANNELS}, got {channel!r}")
    if register not in REGISTERS:
        raise ValueError(f"register must be one of {tuple(REGISTERS)}, got {register!r}")
    forms = REGISTERS[register]
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in (hashtags or [])[:3]) or "[hashtag]"
    if channel == "tiktok":
        beats = "\n".join(
            f"- Ý {i}: {p}\n  Hình: [minh họa cho ý {i}]" for i, p in enumerate(points, 1)
        ) or "- [các ý chính]"
        bullets = ""
    else:
        beats = ""
        bullets = "\n\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)) or "[các ý chính]"
    return _TEMPLATES[channel].format(
        title=title, hook=hook, points=bullets, beats=beats, cta=cta, link=link,
        hashtags=tags, **forms)


def check(text: str) -> dict:
    """Register drift and AI-writing tells for a finished piece (vi_prose)."""
    return vi_prose.lint_text(text)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--channel", choices=CHANNELS, required=True)
    r.add_argument("--register", choices=tuple(REGISTERS), default="peer")
    r.add_argument("--title", required=True)
    r.add_argument("--hook", required=True)
    r.add_argument("--point", action="append", default=[])
    r.add_argument("--cta", required=True)
    r.add_argument("--link", default="[liên kết bài]")
    r.add_argument("--hashtag", action="append", default=[])
    c = sub.add_parser("check")
    c.add_argument("path", type=Path)
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if args.cmd == "render":
        print(render(args.channel, args.register, title=args.title, hook=args.hook,
                     points=args.point, cta=args.cta, link=args.link, hashtags=args.hashtag))
        return 0
    result = check(args.path.read_text(encoding="utf-8"))
    reg = result["register"]
    print(f"Xưng hô chủ đạo: {reg['dominant']}; nhất quán: {'có' if reg['consistent'] else 'KHÔNG'}")
    print(f"Dấu hiệu văn AI: {result['ai_tell_count']}")
    for f in result["findings"]:
        print(f"  dòng {f['line']}: {f['label']}: {f['fix']}")
    return 0 if reg["consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
