#!/usr/bin/env python3
"""Vietnamese content-compliance checks shared by Gate 4 and Gate 5.

One implementation, two callers: ``draft_rubric.legal_disclosure_p0`` (Gate 4
P0) and ``blog_preflight.gate_5_asset_link_integrity`` (Gate 5). Both must
agree, so neither carries its own copy of the rules.

This is a practical checklist, not legal advice. See
``skills/blog/references/vi-compliance.md`` for the sources and for what could
not be verified against a primary text.

Frontmatter keys read here (all optional; a post without them is untouched):

    sponsored: true      paid or sponsored content
    affiliate: true      affiliate / commission links
    topic_class: health | finance | realestate | cosmetics | general

Trigger phrases are matched on diacritic-stripped, lowercased text so that
"thực phẩm chức năng", "thuc pham chuc nang" and NFD input all match.

Stdlib only.
"""

from __future__ import annotations

import re
from typing import Any

import vi_text

TOPIC_CLASSES = ("health", "finance", "realestate", "cosmetics", "general")

_TRUE = {"true", "yes", "y", "1", "co", "on"}

#: Suggested wording. These are drafting aids that satisfy the detector, not
#: quotations of statute; the sponsor line must name the real sponsor.
SPONSORED_SENTENCE = (
    "Bài viết này là nội dung quảng cáo (tài trợ) được thực hiện với sự tài trợ "
    "của [tên nhà tài trợ]."
)
AFFILIATE_SENTENCE = (
    "Bài viết này có chứa liên kết tiếp thị (affiliate): chúng tôi có thể nhận "
    "hoa hồng khi bạn mua hàng qua các liên kết này, giá bạn trả không thay đổi."
)
FUNCTIONAL_FOOD_SENTENCE = (
    "Sản phẩm này không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh."
)

# Patterns run on ascii-folded lowercase text.
_SPONSORED_MARKERS = re.compile(
    r"(?:noi dung|bai viet|bai|tin)\s+(?:nay\s+)?(?:la\s+)?(?:co\s+)?(?:duoc\s+)?"
    r"(?:quang cao|tai tro|pr\b|hop tac quang cao)"
    r"|tai tro\s+(?:boi|tu)\b|\bduoc tai tro\b|\bsponsored\b|paid partnership"
    r"|\bpr\s*/\s*quang cao\b|\bquang cao\s*:",
)
_AFFILIATE_MARKERS = re.compile(
    r"lien ket tiep thi|tiep thi lien ket|\baffiliate\b|hoa hong"
    r"|link (?:tiep thi|gioi thieu)|lien ket gioi thieu",
)
_FUNCTIONAL_FOOD = re.compile(
    r"thuc pham (?:chuc nang|bao ve suc khoe|bo sung)|\btpcn\b|\btpbvsk\b|functional food",
)
_DISCLAIMER_NOT_DRUG = re.compile(r"khong phai (?:la )?thuoc")
_DISCLAIMER_NOT_REPLACE = re.compile(r"(?:khong co tac dung |khong thay the |thay the )(?:cac |cho )?(?:thuoc|phuong phap)")


def fold(text: str) -> str:
    """Lowercase, NFC-normalise and strip diacritics (đ becomes d)."""
    return vi_text.to_ascii(vi_text.normalize(text)).lower()


def is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return fold(str(value or "")).strip() in _TRUE


def topic_class(frontmatter: dict[str, Any]) -> str:
    value = fold(str(frontmatter.get("topic_class", "") or "")).strip()
    return value if value in TOPIC_CLASSES else ""


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Flat ``key: value`` frontmatter and the body. Enough for the keys above."""
    match = re.match(r"^﻿?---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}, text
    fm: dict[str, Any] = {}
    for line in match.group(1).split("\n"):
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            value = value.strip()
            if value[:1] in "\"'" and value[-1:] == value[:1] and len(value) > 1:
                value = value[1:-1]
            fm[key.strip()] = value
    return fm, text[match.end():]


def check(frontmatter: dict[str, Any], body: str) -> list[dict[str, str]]:
    """Return [{'code', 'message'}] for each missing disclosure. Empty = compliant.

    Messages are Vietnamese and end with the exact sentence to add.
    """
    findings: list[dict[str, str]] = []
    text = fold(body)

    if is_true(frontmatter.get("sponsored")) and not _SPONSORED_MARKERS.search(text):
        findings.append({
            "code": "legal_disclosure_sponsored",
            "message": (
                "Bài có sponsored: true nhưng không có khối khai báo nội dung quảng cáo/tài trợ "
                "(Luật Quảng cáo sửa đổi, hiệu lực 01/01/2026). Thêm gần đầu bài câu sau, "
                f"thay phần trong ngoặc bằng tên nhà tài trợ thật: \"{SPONSORED_SENTENCE}\""
            ),
        })
    if is_true(frontmatter.get("affiliate")) and not _AFFILIATE_MARKERS.search(text):
        findings.append({
            "code": "legal_disclosure_affiliate",
            "message": (
                "Bài có affiliate: true nhưng không có khai báo liên kết tiếp thị "
                "(Luật Quảng cáo sửa đổi, hiệu lực 01/01/2026). Thêm gần đầu bài, trước liên kết "
                f"đầu tiên, câu sau: \"{AFFILIATE_SENTENCE}\""
            ),
        })
    if topic_class(frontmatter) == "health" and _FUNCTIONAL_FOOD.search(text):
        if not (_DISCLAIMER_NOT_DRUG.search(text) and _DISCLAIMER_NOT_REPLACE.search(text)):
            findings.append({
                "code": "legal_disclosure_functional_food",
                "message": (
                    "Bài topic_class: health nhắc đến thực phẩm chức năng nhưng thiếu lời khuyến cáo "
                    "(Thông tư 09/2015/TT-BYT). Thêm nguyên văn câu sau, đặt ở cuối bài hoặc ngay "
                    f"sau đoạn nhắc đến sản phẩm: \"{FUNCTIONAL_FOOD_SENTENCE}\""
                ),
            })
    return findings
