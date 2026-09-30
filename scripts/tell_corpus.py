#!/usr/bin/env python3
"""Tell corpus (Phase O): one JSON line per Vietnamese draft analysis.

``analyze_blog.py`` calls ``maybe_record()`` after scoring a draft. The line
goes to ``<workspace>/.metrics/tells.jsonl`` and holds what the model produced
(the phrases that matched, counts, scores, and a few repeated three-syllable
fragments), never the post body. The hub's
``tools/tells_report.py`` reads it monthly so an operator can promote recurring
phrases into ``vi_profile.VI_TELLS``.

Rules:
* Only ``lang: vi`` drafts in draft mode.
* Only when the input path has a ``blog-results`` component, or ``--record``
  is passed, so tests and ad-hoc runs do not pollute the corpus.
* Never fatal: every failure returns None silently.
* Re-analysing an unchanged file (same content hash) appends nothing.

Location: ``$BLOG_TELLS_FILE`` if set; else ``<parent of blog-results>/.metrics/
tells.jsonl``; else, with ``--record`` only, ``./.metrics/tells.jsonl`` if the
cwd has a ``blog-results`` directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

ENV_VAR = 'BLOG_TELLS_FILE'
SCHEMA = 1


def _blog_results_parent(path: Path) -> Path | None:
    parts = path.resolve().parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == 'blog-results':
            return Path(*parts[:i]) if i else None
    return None


def corpus_path(input_path: str | Path, record: bool = False) -> Path | None:
    """Where the corpus lives for this input, or None when nothing may be written."""
    env = os.environ.get(ENV_VAR)
    under = _blog_results_parent(Path(input_path))
    if not (under or record):
        return None
    if env:
        return Path(env).expanduser()
    if under:
        return under / '.metrics' / 'tells.jsonl'
    cwd = Path.cwd()
    if (cwd / 'blog-results').is_dir():
        return cwd / '.metrics' / 'tells.jsonl'
    return None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


_TOKEN = re.compile(r'[^\W\d_]+')
_SENT_SPLIT = re.compile(r'[.!?;:\n]+')
#: Function words; an n-gram with two or more of them is grammar, not a tell.
_STOP = frozenset(
    'và của là có cho một những các được trong để với không này khi thì mà cũng như từ '
    'đã sẽ bạn mình ra vào lên đến nên nếu hay hoặc còn rất đó cần khác hơn theo về'.split()
)
MAX_CANDIDATES = 25


def candidate_phrases(raw_text: str) -> dict[str, int]:
    """Three-syllable phrases a draft repeats, plus sentence openers it repeats.

    These are fragments, not the post: only sequences that occur two or more
    times in one draft, capped at MAX_CANDIDATES. Across many posts the same
    fragment recurring is what tells_report.py surfaces as a possible new tell.
    """
    try:
        import vi_prose
        text = vi_prose._strip_markdown(raw_text)
    except Exception:  # noqa: BLE001
        text = raw_text
    grams: dict[str, int] = {}
    openers: dict[str, int] = {}
    for sentence in _SENT_SPLIT.split(text):
        toks = [t.lower() for t in _TOKEN.findall(sentence)]
        for i in range(len(toks) - 2):
            tri = toks[i:i + 3]
            if sum(t in _STOP for t in tri) >= 2:
                continue
            key = ' '.join(tri)
            grams[key] = grams.get(key, 0) + 1
            if i == 0:
                openers[key] = openers.get(key, 0) + 1
    out = {k: v for k, v in grams.items() if v >= 2}
    out.update({k: max(out.get(k, 0), v) for k, v in openers.items() if v >= 2})
    top = sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_CANDIDATES]
    return dict(top)


def build_entry(result: dict[str, Any], raw_text: str, now: float | None = None) -> dict[str, Any]:
    """Distil an analyze_file() result into a corpus row (no body text)."""
    fm = result.get('frontmatter') or {}
    score = result.get('score') or {}
    phrases: dict[str, int] = {}
    for it in (result.get('lexical_tells') or {}).get('items', []):
        key = str(it.get('match', '')).strip().lower()
        if key:
            phrases[key] = phrases.get(key, 0) + int(it.get('count', 1))
    for it in (result.get('ai_trigger_words') or {}).get('found', []):
        key = str(it.get('word', '')).strip().lower()
        if key:
            phrases[key] = max(phrases.get(key, 0), int(it.get('count', 1)))
    struct = result.get('ai_structure') or {}
    reg = result.get('vi_register') or {}
    file_ = Path(str(result.get('file', '')))
    slug = str(fm.get('slug') or file_.stem)
    return {
        'v': SCHEMA,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(now)),
        'slug': slug,
        'lang': result.get('language', 'vi'),
        'score': score.get('total'),
        'p0': [p if isinstance(p, str) else (p.get('code') or p.get('message') or str(p))
               for p in score.get('p0', [])],
        'phrases': phrases,
        'candidates': candidate_phrases(raw_text),
        'register': {
            'dominant': reg.get('dominant_register'),
            'consistent': reg.get('consistent'),
            'drift_registers': reg.get('drift_registers', []),
            'sentence_counts': reg.get('sentence_counts', {}),
        },
        'structure': {
            'cluster_score': struct.get('cluster_score'),
            'finding_count': struct.get('finding_count'),
            'checks': struct.get('checks_summary', {}),
        },
        'hash': content_hash(raw_text),
    }


def _already_recorded(path: Path, digest: str) -> bool:
    if not path.exists():
        return False
    needle = f'"hash": "{digest}"'
    with path.open(encoding='utf-8') as fh:
        return any(needle in line for line in fh)


def maybe_record(input_path: str | Path, result: dict[str, Any], record: bool = False) -> Path | None:
    """Append one row when the rules allow. Returns the file written, else None."""
    try:
        if result.get('error') or result.get('language') != 'vi':
            return None
        if (result.get('mode') or (result.get('score') or {}).get('mode')) != 'draft':
            return None
        if Path(input_path).stem.lower() == 'review':   # the reviewer's report, not a draft
            return None
        target = corpus_path(input_path, record)
        if target is None:
            return None
        raw = Path(input_path).read_text(encoding='utf-8')
        entry = build_entry(result, raw)
        target.parent.mkdir(parents=True, exist_ok=True)
        if _already_recorded(target, entry['hash']):
            return None
        with target.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return target
    except Exception:  # noqa: BLE001 - recording must never break an analysis
        return None
