#!/usr/bin/env python3
"""Vietnamese text primitives. Standard library only.

Every Vietnamese-specific text operation in this repository routes through this
module. Keeping the logic here (rather than inline in analyzers) means it ports
to other harnesses unchanged and can be tested in isolation.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize", "to_ascii", "slugify", "count_syllables", "is_vietnamese"]

# Characters no Unicode decomposition (canonical or compatibility) can split
# apart: the mark is part of the glyph, not a combining character. Without this
# map, unicodedata + ASCII-encode deletes them.
_UNDECOMPOSABLE = {
    "Đ": "D",   # Vietnamese D with stroke
    "đ": "d",
    "Ð": "D",   # U+00D0 ETH, visually identical, occasionally pasted in
    "ð": "d",
    "ı": "i",   # Turkish dotless i (U+0131), also undecomposable
    "İ": "I",
    "ø": "o",
    "Ø": "O",
    "ß": "ss",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
}

# Precomposed Vietnamese letters, for the detection heuristic. Tone marks stacked
# on horn/breve vowels are the strongest single signal that Latin text is
# Vietnamese rather than any other language.
_VI_MARKERS = (
    "ăâêôơưđ"
    "áàảãạ" "ắằẳẵặ" "ấầẩẫậ"
    "éèẻẽẹ" "ếềểễệ"
    "íìỉĩị"
    "óòỏõọ" "ốồổỗộ" "ớờởỡợ"
    "úùủũụ" "ứừửữự"
    "ýỳỷỹỵ"
)
_VI_MARKER_RE = re.compile(f"[{_VI_MARKERS}]", re.IGNORECASE)

# Frequent Vietnamese function words. Used only to break ties on short input
# where the diacritic ratio is statistically unreliable.
_VI_STOPWORDS = frozenset(
    "và của là có cho các một những được với trong khi này đó người "
    "không như để từ về theo tại cũng đã sẽ nhưng nếu thì mà bạn".split()
)


def normalize(text: str) -> str:
    """Return NFC-normalized text.

    Vietnamese arrives in both NFC (Windows, most CMSes) and NFD (macOS
    filesystems, some editors). The two are visually identical and compare
    unequal. Normalize at every boundary.
    """
    return unicodedata.normalize("NFC", text)


def to_ascii(text: str) -> str:
    """Strip Vietnamese diacritics, preserving d with stroke as plain d.

    ``unicodedata.normalize("NFD", ...).encode("ascii", "ignore")`` alone deletes
    U+0111/U+0110 because neither has a canonical decomposition.
    """
    for src, dst in _UNDECOMPOSABLE.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", stripped)


def slugify(text: str, *, fallback: str = "post") -> str:
    """Return a lowercase, hyphen-separated, ASCII-only URL slug.

    Handles Vietnamese, English and Turkish input identically: transliterate,
    then reduce to ``[a-z0-9-]``.
    """
    ascii_text = to_ascii(normalize(text)).lower()
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9\s\-]", "", ascii_text)
    ascii_text = re.sub(r"[\s_]+", "-", ascii_text)
    ascii_text = re.sub(r"-+", "-", ascii_text).strip("-")
    return ascii_text or fallback


def count_syllables(text: str) -> int:
    """Count Vietnamese syllables.

    Vietnamese orthography writes one syllable per whitespace-separated token, so
    syllable counting is tokenization. This is why English syllable-based
    readability formulas produce meaningless results on Vietnamese: they estimate
    syllables from vowel clusters and always land near 1.0.
    """
    return len(re.findall(r"[^\W\d_]+", normalize(text), re.UNICODE))


def is_vietnamese(text: str, *, min_ratio: float = 0.015, min_markers: int = 3) -> bool:
    """Heuristic Vietnamese detection.

    Mirrors the shape of the existing Turkish heuristic in ``analyze_blog.py``:
    count language-specific characters, require both an absolute floor and a
    ratio against total letters. Falls back to a stopword check for short input
    where the ratio is unstable.
    """
    text = normalize(text)
    markers = len(_VI_MARKER_RE.findall(text))
    letters = len(re.findall(r"[^\W\d_]", text, re.UNICODE))
    if letters == 0:
        return False
    if markers >= min_markers and markers / letters >= min_ratio:
        return True
    tokens = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)
    if len(tokens) >= 8:
        hits = sum(1 for t in tokens if t in _VI_STOPWORDS)
        return hits / len(tokens) >= 0.08
    return False
