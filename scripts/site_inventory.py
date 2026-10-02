#!/usr/bin/env python3
"""Site inventory: what a client website already has (posts, pages, products).

Usage:
    python3 scripts/site_inventory.py init <url> [--brand B] [--author A]
                                       [--canonical-pattern URL] [--force]
    python3 scripts/site_inventory.py refresh [--site d] [--limit N] [--no-fetch-pages]
    python3 scripts/site_inventory.py import-csv <file> [--site d]
    python3 scripts/site_inventory.py add <url> [--title T] [--type post] [--fetch]
    python3 scripts/site_inventory.py search "<query>" [--type product] [--top 10]
    python3 scripts/site_inventory.py gaps [--site d] [--top N] [--volumes] [--json]
    python3 scripts/site_inventory.py stale [--site d] [--top N] [--drafts DIR] [--json]
    python3 scripts/site_inventory.py overlap [--site d] [--top N] [--threshold T] [--drafts DIR]
    python3 scripts/site_inventory.py list-sites
    python3 scripts/site_inventory.py status [--site d]

Layout (under ``workspace/sites/<domain>/``, or ``$CLAUDE_BLOG_SITES_ROOT``):

    site.toml        tracked configuration
    inventory.csv    tracked, one row per URL, opened in Excel by the marketer
    inventory.json   generated, git-ignored
    cache/           raw fetch cache, git-ignored

Rules this module keeps:

* A refresh never overwrites an editable column (focus_keyword, anchors,
  priority, exclude, notes). A URL that vanished stays with ``type=gone``.
  A refresh cut short by ``--limit`` never marks anything gone.
* Structured sources first (WordPress REST, WooCommerce Store API, Shopify and
  Haravan ``/products.json``, Blogger feed), sitemap plus page HTML second.
* Public addresses only, http and https only, no redirect to another host,
  robots.txt honoured, one request at a time with a delay.
* Fetched content is untrusted data. Only extracted fields are stored, each
  truncated; nothing in it is ever treated as an instruction.

Pure helpers other scripts import: ``sites_root``, ``load_inventory``,
``find_site_for_host``, ``load_site_config``, ``tokenize``, ``search``,
``merge_inventory``, ``norm_url``.

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import gzip
import hashlib
import html as html_lib
import io
import json
import math
import os
import re
import socket
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vi_text import is_vietnamese, normalize, to_ascii  # noqa: E402
from generate_hero import _PinnedDNS, _resolve_public_url  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "ClaudeBlogSiteInventory/1.0 (+https://github.com/hxbac/claude-blog; polite, robots.txt aware)"
ROBOTS_TOKEN = "ClaudeBlogSiteInventory"
REQUEST_DELAY = 0.5
HTTP_TIMEOUT = 15
MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_HTML_PARSE = 600 * 1024
DEFAULT_PAGE_CAP = 2000
MAX_REDIRECTS = 3
MAX_SITEMAP_DEPTH = 3

GENERATED = ["url", "type", "title", "h1", "description", "category", "price",
             "in_stock", "lastmod", "lang", "source", "fetched_at"]
EDITABLE = ["focus_keyword", "anchors", "priority", "exclude", "notes"]
COLUMNS = GENERATED + EDITABLE
TYPES = ("post", "product", "category", "page", "tag", "other", "gone")

FIELD_LIMITS = {"url": 500, "title": 200, "h1": 200, "description": 400,
                "category": 150, "price": 40, "in_stock": 8, "lastmod": 40,
                "lang": 12, "source": 24, "fetched_at": 25,
                "focus_keyword": 120, "anchors": 400, "priority": 2,
                "exclude": 8, "notes": 400, "type": 12}

# Rows added by hand are not in any sitemap; a refresh must not call them gone.
MANUAL_SOURCES = ("manual", "csv")


class InventoryError(Exception):
    """A step failed. The message is Vietnamese and safe to show."""


class FetchError(InventoryError):
    pass


# ---------------------------------------------------------------------------
# Paths and site folders
# ---------------------------------------------------------------------------

def sites_root() -> Path:
    """``$CLAUDE_BLOG_SITES_ROOT`` if set, else ``./sites`` (run from workspace/)."""
    env = os.environ.get("CLAUDE_BLOG_SITES_ROOT", "").strip()
    return Path(env).expanduser() if env else Path.cwd() / "sites"


def host_key(host: str) -> str:
    host = (host or "").lower().strip().rstrip(".")
    host = host.split(":")[0] if host.count(":") == 1 else host
    return host[4:] if host.startswith("www.") else host


def domain_dirname(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    name = re.sub(r"[^a-z0-9.-]", "", host_key(host))
    if not name:
        raise InventoryError("Không đọc được tên miền từ địa chỉ này.")
    return name


def list_sites(root: Optional[Path] = None) -> list[Path]:
    root = root or sites_root()
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "site.toml").is_file())


def load_site_config(site_dir: Path) -> dict:
    path = Path(site_dir) / "site.toml"
    try:
        with open(path, "rb") as fh:
            cfg = tomllib.load(fh)
    except FileNotFoundError:
        raise InventoryError(f"Không thấy {path}. Chạy init trước.")
    except tomllib.TOMLDecodeError as exc:
        raise InventoryError(f"site.toml bị lỗi cú pháp: {exc}")
    cfg.setdefault("cms", "other")
    for key in ("sitemaps", "include", "exclude"):
        cfg.setdefault(key, [])
    return cfg


def find_site_for_host(host: str, root: Optional[Path] = None) -> Optional[Path]:
    """Folder of the configured site whose base_url host equals ``host``
    (``www.`` ignored, port ignored), or None."""
    want = host_key(host)
    if not want:
        return None
    for site_dir in list_sites(root):
        try:
            cfg = load_site_config(site_dir)
        except InventoryError:
            continue
        base_host = urllib.parse.urlparse(cfg.get("base_url", "")).hostname or ""
        if host_key(base_host) == want or site_dir.name == want:
            return site_dir
    return None


def resolve_site(arg: Optional[str], root: Optional[Path] = None) -> Path:
    """``--site`` may be a folder name, a domain, or a path. With no argument the
    only configured site is used; with several the caller must choose."""
    root = root or sites_root()
    if arg:
        p = Path(arg)
        if (p / "site.toml").is_file():
            return p
        if (root / arg / "site.toml").is_file():
            return root / arg
        found = find_site_for_host(arg, root)
        if found:
            return found
        raise InventoryError(f"Không tìm thấy web '{arg}' trong {root}. Xem: list-sites")
    sites = list_sites(root)
    if not sites:
        raise InventoryError(f"Chưa có web nào trong {root}. Chạy: init <địa chỉ web>")
    if len(sites) > 1:
        names = ", ".join(s.name for s in sites)
        raise InventoryError(f"Có {len(sites)} web ({names}). Chọn một bằng --site.")
    return sites[0]


# ---------------------------------------------------------------------------
# Text hygiene (everything fetched is untrusted)
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")


def clean_text(value: object, limit: int = 200) -> str:
    """Plain, single-line, NFC text, truncated. Strips tags and control and
    bidi characters, and leading characters a spreadsheet would run as a formula."""
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = _CTRL_RE.sub(" ", text)
    text = normalize(" ".join(text.split()))
    text = text.lstrip("=+-@ ")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def blank_row() -> dict:
    return {c: "" for c in COLUMNS}


def clamp_row(row: dict) -> dict:
    out = dict(row)
    for col, lim in FIELD_LIMITS.items():
        if col in out and isinstance(out[col], str) and len(out[col]) > lim:
            out[col] = out[col][:lim]
    return out


# ---------------------------------------------------------------------------
# URLs and classification
# ---------------------------------------------------------------------------

_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_)", re.I)


def norm_url(url: str) -> str:
    """Key for comparing URLs: lowercase scheme and host, no fragment, no default
    port, no tracking params, no trailing slash (except the root)."""
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    port = p.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = p.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not _TRACKING.match(k)])
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def same_site(url: str, base_url: str) -> bool:
    a = urllib.parse.urlparse(url).hostname or ""
    b = urllib.parse.urlparse(base_url).hostname or ""
    return bool(a) and host_key(a) == host_key(b)


_SITEMAP_HINTS = [
    (re.compile(r"product[_-]?cat|collection|danh-?muc|taxonomies-product_cat|categor", re.I), "category"),
    (re.compile(r"post[_-]?tag|tags?[-_.]|taxonomies-post_tag", re.I), "tag"),
    (re.compile(r"product", re.I), "product"),
    (re.compile(r"blog|post|article|news|tin-?tuc", re.I), "post"),
    (re.compile(r"page", re.I), "page"),
]


def sitemap_hint(sitemap_url: str) -> Optional[str]:
    name = urllib.parse.urlparse(sitemap_url).path.rsplit("/", 1)[-1]
    for pattern, kind in _SITEMAP_HINTS:
        if pattern.search(name):
            return kind
    return None


_PATH_RULES = [
    ("product", re.compile(r"/(products?|san-pham|sp)/[^/]+", re.I)),
    ("tag", re.compile(r"/(tags?|the|tagged|chu-de)/", re.I)),
    ("category", re.compile(r"/(category|categories|product-category|danh-muc|chuyen-muc|collections?)/", re.I)),
    ("post", re.compile(r"/(blogs?|tin-tuc|bai-viet|kien-thuc|news|articles?|huong-dan)/[^/]+|/\d{4}/\d{2}/", re.I)),
]


def classify(url: str, hint: Optional[str] = None, og_type: str = "",
             has_product_ld: bool = False) -> str:
    """post|product|category|page|tag|other. Page evidence beats the sitemap
    file name, which beats URL patterns."""
    if has_product_ld or og_type.lower() == "product":
        return "product"
    if og_type.lower() == "article":
        return "post"
    if hint:
        return hint
    path = urllib.parse.urlparse(url).path or "/"
    for kind, rx in _PATH_RULES:
        if rx.search(path):
            return kind
    if path in ("", "/"):
        return "page"
    if path.rstrip("/").count("/") == 1 and "." not in path:
        return "page"
    return "other"


def url_allowed(url: str, include: list, exclude: list) -> bool:
    p = urllib.parse.urlparse(url)
    target = p.path + (f"?{p.query}" if p.query else "")
    if any(fnmatch.fnmatch(target, pat) for pat in exclude):
        return False
    if include:
        return any(fnmatch.fnmatch(target, pat) for pat in include)
    return True


# ---------------------------------------------------------------------------
# HTTP layer (SSRF guarded). Tests replace Fetcher's `transport`.
# ---------------------------------------------------------------------------

@dataclass
class Response:
    status: int
    headers: dict
    body: bytes
    url: str
    cached: bool = False

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except (ValueError, UnicodeError):
            return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def http_get(url: str, headers: Optional[dict] = None, *, max_bytes: int = MAX_BODY_BYTES,
             timeout: int = HTTP_TIMEOUT) -> Response:
    """One GET. Every hop is checked for a public address; redirects are followed
    by hand, only within the same site (``www.`` equivalent), at most 3 times."""
    current = url
    origin_host = urllib.parse.urlparse(url).hostname or ""
    for _hop in range(MAX_REDIRECTS + 1):
        ok, reason, host, port, infos = _resolve_public_url(current)
        if not ok or host is None or port is None:
            raise FetchError(f"Từ chối truy cập địa chỉ này ({reason}).")
        req = urllib.request.Request(current, headers={"User-Agent": USER_AGENT, **(headers or {})})
        try:
            with _PinnedDNS(host, port, infos):
                with _OPENER.open(req, timeout=timeout) as resp:
                    body = resp.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise FetchError("Phản hồi quá lớn, bỏ qua.")
                    hdrs = {k.lower(): v for k, v in resp.headers.items()}
                    return Response(int(getattr(resp, "status", 200)), hdrs, body, current)
        except urllib.error.HTTPError as exc:
            hdrs = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
            if exc.code in (301, 302, 303, 307, 308) and hdrs.get("location"):
                nxt = urllib.parse.urljoin(current, hdrs["location"])
                if urllib.parse.urlparse(nxt).scheme not in ("http", "https"):
                    raise FetchError("Chuyển hướng tới địa chỉ không hợp lệ.")
                if host_key(urllib.parse.urlparse(nxt).hostname or "") != host_key(origin_host):
                    raise FetchError("Web chuyển hướng sang tên miền khác, đã dừng.")
                current = nxt
                continue
            return Response(exc.code, hdrs, b"", current)
        except FetchError:
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
            raise FetchError(f"Không kết nối được tới {urllib.parse.urlparse(current).hostname}: {exc}")
    raise FetchError("Chuyển hướng quá nhiều lần.")


class Fetcher:
    """Polite fetching: robots.txt, one request at a time, delay, conditional GET."""

    def __init__(self, base_url: str, *, cache_dir: Optional[Path] = None,
                 transport: Optional[Callable[..., Response]] = None,
                 delay: float = REQUEST_DELAY, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.transport = transport or http_get
        self.delay = delay
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self._robots: Optional[urllib.robotparser.RobotFileParser] = None
        self.requests = 0
        self.robots_blocked: list = []
        self.sitemaps_from_robots: list = []

    # robots.txt
    def _load_robots(self) -> None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = self._raw(self.base_url + "/robots.txt", {})
        except FetchError:
            rp.disallow_all = True
            self._robots = rp
            return
        if resp.status == 200:
            rp.parse(resp.body.decode("utf-8", "replace").splitlines())
            self.sitemaps_from_robots = list(rp.site_maps() or [])
        elif 400 <= resp.status < 500:
            rp.allow_all = True
        else:
            rp.disallow_all = True
        self._robots = rp

    def allowed(self, url: str) -> bool:
        if self._robots is None:
            self._load_robots()
        return self._robots.can_fetch(ROBOTS_TOKEN, url)

    # cache
    def _cache_paths(self, url: str):
        if not self.cache_dir:
            return None, None
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.body"

    def _cache_load(self, url: str):
        meta_p, body_p = self._cache_paths(url)
        if not meta_p or not meta_p.is_file() or not body_p.is_file():
            return None
        try:
            return json.loads(meta_p.read_text(encoding="utf-8")), body_p.read_bytes()
        except (OSError, ValueError):
            return None

    def _cache_save(self, url: str, resp: Response) -> None:
        meta_p, body_p = self._cache_paths(url)
        if not meta_p:
            return
        etag = resp.headers.get("etag", "")
        modified = resp.headers.get("last-modified", "")
        if not (etag or modified):
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            body_p.write_bytes(resp.body)
            meta_p.write_text(json.dumps({"url": url, "etag": etag, "last_modified": modified,
                                          "fetched_at": now_iso(), "status": resp.status},
                                         ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # requests
    def _raw(self, url: str, headers: dict) -> Response:
        if self._last is not None:
            wait = self.delay - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self.requests += 1
        try:
            return self.transport(url, headers)
        finally:
            self._last = self._clock()

    def get(self, url: str, *, accept: str = "") -> Response:
        """GET with robots check, delay and conditional cache. A robots refusal
        raises FetchError (and is counted); other HTTP statuses are returned."""
        if not self.allowed(url):
            self.robots_blocked.append(url)
            raise FetchError("robots.txt không cho phép lấy địa chỉ này.")
        headers = {"Accept": accept} if accept else {}
        cached = self._cache_load(url)
        if cached:
            meta, _ = cached
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]
        resp = self._raw(url, headers)
        if resp.status == 304 and cached:
            return Response(200, {"etag": cached[0].get("etag", "")}, cached[1], url, cached=True)
        if resp.status == 200:
            self._cache_save(url, resp)
        return resp


# ---------------------------------------------------------------------------
# HTML extraction (only these fields are kept)
# ---------------------------------------------------------------------------

class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1 = ""
        self.meta: dict = {}
        self.canonical = ""
        self.lang = ""
        self.jsonld: list = []
        self._in = None
        self._buf: list = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html" and not self.lang:
            self.lang = a.get("lang", "")
        elif tag == "title" and not self.title:
            self._in, self._buf = "title", []
        elif tag == "h1" and not self.h1:
            self._in, self._buf = "h1", []
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and key not in self.meta:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split() and not self.canonical:
            self.canonical = a.get("href", "")
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in, self._buf = "ld", []

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._in == "title" and tag == "title":
            self.title = "".join(self._buf)
            self._in = None
        elif self._in == "h1" and tag == "h1":
            self.h1 = "".join(self._buf)
            self._in = None
        elif self._in == "ld" and tag == "script":
            self.jsonld.append("".join(self._buf))
            self._in = None


def _walk_ld(node, found: list) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_ld(item, found)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        found.append((kinds, node))
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                _walk_ld(node[key], found)


def _offer_price(offers) -> tuple[str, str, str]:
    if isinstance(offers, list):
        offers = next((o for o in offers if isinstance(o, dict)), {})
    if not isinstance(offers, dict):
        return "", "", ""
    price = offers.get("price") or offers.get("lowPrice") or ""
    cur = offers.get("priceCurrency") or ""
    avail = str(offers.get("availability") or "")
    stock = "yes" if "InStock" in avail else ("no" if avail else "")
    return str(price), str(cur), stock


def extract_page(html_text: str) -> dict:
    """Pull the few fields we keep out of untrusted HTML."""
    parser = _PageParser()
    try:
        parser.feed(html_text[:MAX_HTML_PARSE])
        parser.close()
    except Exception:  # malformed markup must never abort a refresh
        pass
    if parser._in == "title" and not parser.title:  # unclosed <title>
        parser.title = "".join(parser._buf)
    elif parser._in == "h1" and not parser.h1:
        parser.h1 = "".join(parser._buf)
    out = {
        "title": clean_text(parser.title, FIELD_LIMITS["title"]),
        "h1": clean_text(parser.h1, FIELD_LIMITS["h1"]),
        "description": clean_text(parser.meta.get("description") or parser.meta.get("og:description"),
                                  FIELD_LIMITS["description"]),
        "og_type": clean_text(parser.meta.get("og:type"), 30).lower(),
        "canonical": clean_text(parser.canonical, FIELD_LIMITS["url"]).replace(" ", ""),
        "lang": clean_text(parser.lang or parser.meta.get("og:locale"), 12).replace("_", "-").lower(),
        "site_name": clean_text(parser.meta.get("og:site_name"), 100),
        "price": "", "in_stock": "", "is_product": False,
    }
    found: list = []
    for raw in parser.jsonld[:10]:
        try:
            _walk_ld(json.loads(raw), found)
        except ValueError:
            continue
    for kinds, node in found:
        if "Product" in kinds:
            out["is_product"] = True
            price, cur, stock = _offer_price(node.get("offers"))
            if price and not out["price"]:
                out["price"] = clean_text(f"{price} {cur}".strip(), FIELD_LIMITS["price"])
                out["in_stock"] = stock
    return out


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------

def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(body: bytes) -> tuple[str, list]:
    """Return ("index"|"urlset", [(loc, lastmod), ...]). Rejects DTDs and
    entities (untrusted XML) and gzip bombs."""
    if body[:2] == b"\x1f\x8b":
        try:
            dec = zlib_decompress_limited(body, MAX_BODY_BYTES * 4)
        except (OSError, ValueError):
            return "urlset", []
        body = dec
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body[:65536].lower():
        return "urlset", []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return "urlset", []
    kind = "index" if _localname(root.tag) == "sitemapindex" else "urlset"
    items = []
    for node in root:
        loc = lastmod = ""
        for child in node:
            name = _localname(child.tag)
            if name == "loc":
                loc = (child.text or "").strip()
            elif name == "lastmod":
                lastmod = (child.text or "").strip()
        if loc:
            items.append((loc, lastmod))
    return kind, items


def zlib_decompress_limited(data: bytes, limit: int) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
        out = fh.read(limit + 1)
    if len(out) > limit:
        raise ValueError("gzip too large")
    return out


def collect_sitemap_urls(fetcher: Fetcher, sitemaps: list, base_url: str, *, per_group: int,
                         total_cap: int, skip_hints: tuple = (), depth: int = 0,
                         hint: Optional[str] = None) -> tuple[list, bool]:
    """Walk sitemaps. Returns ([(url, lastmod, hint)], truncated). Only URLs on the
    site's own host are kept."""
    urls: list = []
    truncated = False
    for sm in sitemaps:
        if len(urls) >= total_cap:
            return urls, True
        if not same_site(sm, base_url):
            continue
        h = sitemap_hint(sm) or hint
        if h in skip_hints:
            continue
        try:
            resp = fetcher.get(sm, accept="application/xml,text/xml,*/*")
        except FetchError:
            continue
        if resp.status != 200:
            continue
        kind, items = parse_sitemap(resp.body)
        if kind == "index":
            if depth >= MAX_SITEMAP_DEPTH:
                continue
            got, cut = collect_sitemap_urls(fetcher, [loc for loc, _ in items], base_url,
                                            per_group=per_group, total_cap=total_cap - len(urls),
                                            skip_hints=skip_hints, depth=depth + 1, hint=h)
            urls.extend(got)
            truncated = truncated or cut
            continue
        taken = 0
        for loc, lastmod in items:
            if not same_site(loc, base_url) or urllib.parse.urlparse(loc).scheme not in ("http", "https"):
                continue
            if taken >= per_group or len(urls) >= total_cap:
                truncated = True
                break
            urls.append((loc, lastmod, h))
            taken += 1
    return urls, truncated


# ---------------------------------------------------------------------------
# Structured sources
# ---------------------------------------------------------------------------

def _json_or_none(fetcher: Fetcher, url: str):
    try:
        resp = fetcher.get(url, accept="application/json")
    except FetchError:
        return None, None
    if resp.status != 200:
        return None, resp
    return resp.json(), resp


def _page_loop(fetcher: Fetcher, url_for_page: Callable[[int], str], extract: Callable[[object], list],
               limit: int, per_page: int) -> tuple[list, bool]:
    """Fetch pages until empty, a non-200, the advertised total, or ``limit`` rows."""
    out: list = []
    page = 1
    total_pages = None
    while True:
        data, resp = _json_or_none(fetcher, url_for_page(page))
        if data is None:
            return out, False
        if total_pages is None and resp is not None:
            try:
                total_pages = int(resp.headers.get("x-wp-totalpages", ""))
            except ValueError:
                total_pages = None
        items = extract(data)
        if not items:
            return out, False
        out.extend(items)
        if len(out) >= limit:
            more = not (total_pages is not None and page >= total_pages)
            return out[:limit], len(out) > limit or (len(items) >= per_page and more)
        if len(items) < per_page or (total_pages is not None and page >= total_pages):
            return out, False
        page += 1


def wp_rows(fetcher: Fetcher, base: str, limit: int, lang: str) -> tuple[list, bool, bool]:
    """WordPress REST: posts, pages, categories. Returns (rows, truncated, api_ok)."""
    rows: list = []
    truncated = False
    per = max(1, min(100, limit))
    stamp = now_iso()
    cats: dict = {}

    def cat_items(data):
        return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []

    cat_list, cut = _page_loop(
        fetcher, lambda p: f"{base}/wp-json/wp/v2/categories?per_page={per}&page={p}&_fields=id,link,name,description,count,slug",
        cat_items, limit, per)
    truncated = truncated or cut
    for c in cat_list:
        cats[c.get("id")] = clean_text(c.get("name"), FIELD_LIMITS["category"])

    api_ok = False
    for kind, ep in (("post", "posts"), ("page", "pages")):
        def items(data):
            return [i for i in data if isinstance(i, dict) and i.get("link")] if isinstance(data, list) else []
        got, cut = _page_loop(
            fetcher, lambda p, ep=ep: f"{base}/wp-json/wp/v2/{ep}?per_page={per}&page={p}&_fields=link,title,excerpt,date,modified,categories",
            items, limit, per)
        truncated = truncated or cut
        api_ok = api_ok or bool(got)
        for it in got:
            r = blank_row()
            r.update(url=clean_text(it["link"], 500).replace(" ", ""), type=kind,
                     title=clean_text((it.get("title") or {}).get("rendered"), FIELD_LIMITS["title"]),
                     description=clean_text((it.get("excerpt") or {}).get("rendered"), FIELD_LIMITS["description"]),
                     category=" | ".join(dict.fromkeys(cats[i] for i in (it.get("categories") or []) if i in cats)),
                     lastmod=clean_text(it.get("modified") or it.get("date"), 40),
                     lang=lang, source="wp-rest", fetched_at=stamp)
            rows.append(r)
    for c in cat_list:
        if not c.get("link"):
            continue
        r = blank_row()
        r.update(url=clean_text(c["link"], 500).replace(" ", ""), type="category",
                 title=clean_text(c.get("name"), FIELD_LIMITS["title"]),
                 description=clean_text(c.get("description"), FIELD_LIMITS["description"]),
                 lang=lang, source="wp-rest", fetched_at=stamp)
        rows.append(r)
    return rows, truncated, api_ok


def woo_rows(fetcher: Fetcher, base: str, limit: int, lang: str) -> tuple[list, bool]:
    """WooCommerce Store API products and product categories."""
    per = max(1, min(100, limit))
    stamp = now_iso()
    rows: list = []

    def items(data):
        return [i for i in data if isinstance(i, dict) and i.get("permalink")] if isinstance(data, list) else []

    prods, truncated = _page_loop(
        fetcher, lambda p: f"{base}/wp-json/wc/store/v1/products?per_page={per}&page={p}", items, limit, per)
    for it in prods:
        prices = it.get("prices") or {}
        price = ""
        try:
            minor = int(prices.get("currency_minor_unit", 0))
            price = str(int(prices.get("price", "")) // (10 ** minor)) if minor == 0 else \
                f"{int(prices.get('price')) / (10 ** minor):g}"
        except (TypeError, ValueError):
            price = ""
        cur = clean_text(prices.get("currency_code"), 6)
        cats = [clean_text(c.get("name"), FIELD_LIMITS["category"]) for c in (it.get("categories") or [])
                if isinstance(c, dict)]
        r = blank_row()
        r.update(url=clean_text(it["permalink"], 500).replace(" ", ""), type="product",
                 title=clean_text(it.get("name"), FIELD_LIMITS["title"]),
                 description=clean_text(it.get("short_description") or it.get("description"),
                                        FIELD_LIMITS["description"]),
                 category=" | ".join(c for c in cats if c),
                 price=f"{price} {cur}".strip() if price else "",
                 in_stock="yes" if it.get("is_in_stock") else ("no" if "is_in_stock" in it else ""),
                 lang=lang, source="woo-store", fetched_at=stamp)
        rows.append(r)
    cat_items, cut = _page_loop(
        fetcher, lambda p: f"{base}/wp-json/wc/store/v1/products/categories?per_page={per}&page={p}",
        lambda d: [c for c in d if isinstance(c, dict) and c.get("permalink")] if isinstance(d, list) else [],
        limit, per)
    truncated = truncated or cut
    for c in cat_items:
        r = blank_row()
        r.update(url=clean_text(c["permalink"], 500).replace(" ", ""), type="category",
                 title=clean_text(c.get("name"), FIELD_LIMITS["title"]),
                 description=clean_text(c.get("description"), FIELD_LIMITS["description"]),
                 lang=lang, source="woo-store", fetched_at=stamp)
        rows.append(r)
    return rows, truncated


def shop_rows(fetcher: Fetcher, base: str, cms: str, limit: int, lang: str) -> tuple[list, bool]:
    """Shopify and Haravan: /products.json (250 per page) and /collections.json."""
    rows: list = []
    per = max(1, min(250, limit))
    stamp = now_iso()
    cur = "VND" if cms == "haravan" else ""

    def items(data):
        if isinstance(data, dict) and isinstance(data.get("products"), list):
            return [p for p in data["products"] if isinstance(p, dict) and p.get("handle")]
        return []

    prods, truncated = _page_loop(
        fetcher, lambda p: f"{base}/products.json?limit={per}&page={p}", items, limit, per)
    for it in prods:
        variants = [v for v in (it.get("variants") or []) if isinstance(v, dict)]
        prices = []
        for v in variants:
            try:
                prices.append(float(str(v.get("price", "")).replace(",", "")))
            except ValueError:
                continue
        price = f"{min(prices):g}" if prices else ""
        avail = [v.get("available") for v in variants if "available" in v]
        r = blank_row()
        r.update(url=f"{base}/products/{urllib.parse.quote(str(it['handle']), safe='-_.~')}", type="product",
                 title=clean_text(it.get("title"), FIELD_LIMITS["title"]),
                 description=clean_text(it.get("body_html"), FIELD_LIMITS["description"]),
                 category=clean_text(it.get("product_type"), FIELD_LIMITS["category"]),
                 price=f"{price} {cur}".strip() if price else "",
                 in_stock=("yes" if any(avail) else "no") if avail else "",
                 lastmod=clean_text(it.get("updated_at"), 40), lang=lang,
                 source=f"{cms}-json", fetched_at=stamp)
        rows.append(r)

    def coll_items(data):
        if isinstance(data, dict) and isinstance(data.get("collections"), list):
            return [c for c in data["collections"] if isinstance(c, dict) and c.get("handle")]
        return []

    colls, cut = _page_loop(
        fetcher, lambda p: f"{base}/collections.json?limit={per}&page={p}", coll_items, limit, per)
    truncated = truncated or cut
    for c in colls:
        r = blank_row()
        r.update(url=f"{base}/collections/{urllib.parse.quote(str(c['handle']), safe='-_.~')}", type="category",
                 title=clean_text(c.get("title"), FIELD_LIMITS["title"]),
                 description=clean_text(c.get("body_html"), FIELD_LIMITS["description"]),
                 lastmod=clean_text(c.get("updated_at"), 40), lang=lang,
                 source=f"{cms}-json", fetched_at=stamp)
        rows.append(r)
    return rows, truncated


def blogger_rows(fetcher: Fetcher, base: str, limit: int, lang: str) -> tuple[list, bool]:
    rows: list = []
    truncated = False
    stamp = now_iso()
    for kind, feed in (("post", "posts"), ("page", "pages")):
        start = 1
        per = max(1, min(150, limit))
        got = 0
        while got < limit:
            data, _ = _json_or_none(
                fetcher, f"{base}/feeds/{feed}/default?alt=json&max-results={per}&start-index={start}")
            entries = (data or {}).get("feed", {}).get("entry", []) if isinstance(data, dict) else []
            if not entries:
                break
            for e in entries:
                href = next((l.get("href") for l in e.get("link", []) if l.get("rel") == "alternate"), "")
                if not href:
                    continue
                r = blank_row()
                r.update(url=clean_text(href, 500).replace(" ", ""), type=kind,
                         title=clean_text((e.get("title") or {}).get("$t"), FIELD_LIMITS["title"]),
                         description=clean_text((e.get("summary") or {}).get("$t"), FIELD_LIMITS["description"]),
                         category=" | ".join(clean_text(c.get("term"), 60) for c in e.get("category", [])[:3]),
                         lastmod=clean_text((e.get("updated") or {}).get("$t"), 40),
                         lang=lang, source="blogger-feed", fetched_at=stamp)
                rows.append(r)
                got += 1
                if got >= limit:
                    truncated = True
                    break
            if len(entries) < per:
                break
            start += per
    return rows, truncated


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform(fetcher: Fetcher, base: str) -> tuple[str, str, Optional[Response]]:
    """Structured APIs first. Returns (cms, base_url_after_redirects, homepage)."""
    home = None
    try:
        home = fetcher.get(base + "/", accept="text/html")
        if home.status == 200:
            final = urllib.parse.urlsplit(home.url)
            base = f"{final.scheme}://{final.netloc}"
    except FetchError:
        home = None
    html_text = home.body.decode("utf-8", "replace")[:MAX_HTML_PARSE] if home and home.status == 200 else ""

    data, _ = _json_or_none(fetcher, base + "/wp-json/")
    if isinstance(data, dict) and any(str(n).startswith("wp/") for n in data.get("namespaces", [])):
        if any(str(n).startswith("wc/store") for n in data.get("namespaces", [])):
            return "woocommerce", base, home
        return "wordpress", base, home

    data, _ = _json_or_none(fetcher, base + "/products.json?limit=1")
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        low = html_text.lower()
        if "haravan" in low or "hstatic.net" in low:
            return "haravan", base, home
        return "shopify", base, home

    data, _ = _json_or_none(fetcher, base + "/feeds/posts/default?alt=json&max-results=1")
    if isinstance(data, dict) and "feed" in data:
        return "blogger", base, home

    if "/wp-content/" in html_text or "wp-includes" in html_text:
        return "wordpress", base, home
    return "other", base, home


# ---------------------------------------------------------------------------
# CSV storage and merge
# ---------------------------------------------------------------------------

def read_csv_rows(path: Path) -> list:
    """Read an inventory CSV. Tolerates a BOM, CRLF or LF, and the semicolon or
    tab delimiter some Excel locales write. Unknown columns are kept."""
    path = Path(path)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    first = text.splitlines()[0]
    delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return []
    rows = []
    for rec in reader:
        if not any(cell.strip() for cell in rec):
            continue
        row = blank_row()
        for name, cell in zip(header, rec):
            if name:
                row[name] = cell.strip()
        if row.get("url"):
            rows.append(row)
    return rows


def write_csv_rows(path: Path, rows: list) -> None:
    """UTF-8 with BOM (Excel shows Vietnamese correctly), atomic replace."""
    path = Path(path)
    extras = sorted({k for r in rows for k in r if k not in COLUMNS})
    header = COLUMNS + extras
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for r in rows:
        writer.writerow([r.get(c, "") for c in header])
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise InventoryError(
            f"Không ghi được {path.name} ({exc}). Nếu file đang mở trong Excel, hãy đóng lại rồi chạy lại.")


def load_inventory(site_dir) -> list:
    """Rows of ``inventory.csv`` (the source of truth, edits included)."""
    return read_csv_rows(Path(site_dir) / "inventory.csv")


def merge_inventory(existing: list, fresh: list, *, complete: bool = True, now: str = "") -> list:
    """Merge a fresh scan into the stored rows.

    * editable columns are never touched for a URL already stored;
    * a generated column is only replaced by a non-empty fresh value;
    * stored URLs missing from the scan become ``type=gone`` (kept), but only
      when the scan was ``complete``, and never for rows added by hand;
    * a gone URL that reappears is revived.
    """
    now = now or now_iso()
    out = [dict(r) for r in existing]
    index = {norm_url(r["url"]): r for r in out if r.get("url")}
    seen = set()
    for fr in fresh:
        key = norm_url(fr["url"])
        if key in seen:
            continue
        seen.add(key)
        cur = index.get(key)
        if cur is None:
            row = blank_row()
            row.update({c: fr.get(c, "") for c in GENERATED})
            row["fetched_at"] = fr.get("fetched_at") or now
            out.append(row)
            index[key] = row
            continue
        for col in GENERATED:
            if col == "url":
                continue
            val = fr.get(col, "")
            if not val:
                continue
            if col == "type" and val == "other" and cur.get("type") not in ("", "gone", "other"):
                continue
            cur[col] = val
        cur["fetched_at"] = fr.get("fetched_at") or now
    if complete:
        for key, row in index.items():
            if key not in seen and row.get("type") != "gone" and row.get("source") not in MANUAL_SOURCES:
                row["type"] = "gone"
    return out


# ---------------------------------------------------------------------------
# Tokenizing and search
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    """Diacritic-stripped, lowercase syllable unigrams followed by bigrams
    ("may pha", "pha ca"). Vietnamese writes one syllable per word, so the
    unigram is a syllable and the bigram is the nearest thing to a word."""
    words = _WORD_RE.findall(to_ascii(normalize(text or "")).lower())
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


SEARCH_WEIGHTS = {"focus_keyword": 3.0, "anchors": 3.0, "title": 2.0, "h1": 2.0,
                  "description": 1.0, "category": 1.0}


def _row_slug(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")


def row_weights(row: dict) -> dict:
    """Token -> weight for one row (max over the fields it occurs in)."""
    weights: dict = {}
    fields = dict(SEARCH_WEIGHTS)
    for name, w in fields.items():
        text = row.get(name, "")
        if name == "anchors":
            text = text.replace("|", " . ")
        for tok in set(tokenize(text)):
            if weights.get(tok, 0) < w:
                weights[tok] = w
    for tok in set(tokenize(_row_slug(row.get("url", "")))):
        if weights.get(tok, 0) < 1.0:
            weights[tok] = 1.0
    return weights


def idf_table(docs: list) -> dict:
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    return {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}


def search(rows: list, query: str, type: Optional[str] = None, top: int = 10,
           include_gone: bool = False) -> list:
    """Rank rows against a query. Same result with or without diacritics.
    Returns copies of the rows with a ``score`` key, best first."""
    q = Counter(tokenize(query))
    if not q:
        return []
    docs = [row_weights(r) for r in rows]
    idf = idf_table(docs)
    scored = []
    for row, doc in zip(rows, docs):
        if (not include_gone and row.get("type") == "gone") or (type and row.get("type") != type):
            continue
        score = 0.0
        for tok, qn in q.items():
            if tok in doc:
                score += idf.get(tok, 0.0) * doc[tok] * (1.0 + 0.5 * (len(tok.split()) - 1))
        if score > 0:
            item = dict(row)
            item["score"] = round(score, 4)
            scored.append(item)
    scored.sort(key=lambda r: (-r["score"], r.get("url", "")))
    return scored[: max(0, top)]


# ---------------------------------------------------------------------------
# Site files
# ---------------------------------------------------------------------------

def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_site_toml(site_dir: Path, cfg: dict) -> None:
    lines = [
        "# Cấu hình web khách. Sửa tay được.",
        f"base_url = {_toml_str(cfg['base_url'])}",
        f"cms = {_toml_str(cfg['cms'])}   # wordpress | woocommerce | haravan | shopify | blogger | other",
        f"brand = {_toml_str(cfg.get('brand', ''))}",
        f"default_author = {_toml_str(cfg.get('default_author', ''))}",
        f"lang = {_toml_str(cfg.get('lang', ''))}",
    ]
    pattern = cfg.get("canonical_pattern", "")
    if pattern:
        lines.append(f"canonical_pattern = {_toml_str(pattern)}")
    else:
        lines.append('# canonical_pattern = "https://example.vn/blog/{slug}"   # link chuẩn cho bài mới')
    lines += [
        f"sitemaps = {json.dumps(cfg.get('sitemaps', []), ensure_ascii=False)}",
        "# Mẫu đường dẫn, ví dụ \"/blog/*\". include rỗng nghĩa là lấy tất cả.",
        f"include = {json.dumps(cfg.get('include', []), ensure_ascii=False)}",
        f"exclude = {json.dumps(cfg.get('exclude', []), ensure_ascii=False)}",
        "",
    ]
    (site_dir / "site.toml").write_text("\n".join(lines), encoding="utf-8")


def write_inventory_json(site_dir: Path, rows: list) -> None:
    counts = Counter(r.get("type", "") for r in rows)
    data = {"generated_at": now_iso(), "count": len(rows), "types": dict(counts), "rows": rows}
    (Path(site_dir) / "inventory.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def type_counts(rows: list) -> dict:
    return dict(Counter(r.get("type") or "other" for r in rows))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _normalize_input_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urllib.parse.urlsplit(url)
    if not p.hostname:
        raise InventoryError("Địa chỉ web không hợp lệ.")
    return f"{p.scheme.lower()}://{p.netloc.lower()}"


def make_fetcher(base_url: str, site_dir: Optional[Path], transport=None, delay: float = REQUEST_DELAY) -> Fetcher:
    return Fetcher(base_url, cache_dir=(Path(site_dir) / "cache") if site_dir else None,
                   transport=transport, delay=delay)


def cmd_init(args, out=print, transport=None, delay: float = REQUEST_DELAY) -> int:
    base = _normalize_input_url(args.url)
    ok, reason, *_ = _resolve_public_url(base) if transport is None else (True, None)
    if not ok:
        raise InventoryError(f"Từ chối địa chỉ này ({reason}). Chỉ nhận web công khai.")
    root = sites_root()
    site_dir = root / domain_dirname(base)
    if (site_dir / "site.toml").exists() and not args.force:
        raise InventoryError(f"{site_dir.name} đã có cấu hình. Dùng refresh để cập nhật, hoặc init --force để dựng lại site.toml.")
    fetcher = make_fetcher(base, site_dir, transport, delay)
    cms, base, home = detect_platform(fetcher, base)
    site_dir = root / domain_dirname(base)
    fetcher.base_url = base
    page = extract_page(home.body.decode("utf-8", "replace")) if home and home.status == 200 else {}
    lang = (page.get("lang") or "")[:2]
    if not lang and page and is_vietnamese(page.get("title", "") + " " + page.get("description", "")):
        lang = "vi"
    sitemaps: list = []
    for cand in fetcher.sitemaps_from_robots:
        if same_site(cand, base) and cand not in sitemaps:
            sitemaps.append(cand)
    if not sitemaps:
        for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
            try:
                resp = fetcher.get(base + path, accept="application/xml,text/xml,*/*")
            except FetchError:
                continue
            if resp.status == 200 and parse_sitemap(resp.body)[1]:
                sitemaps.append(base + path)
                break
    cfg = {"base_url": base, "cms": cms, "lang": lang, "sitemaps": sitemaps,
           "brand": args.brand or page.get("site_name") or (page.get("title", "").split("|")[0].strip()[:80]),
           "default_author": args.author or "", "canonical_pattern": args.canonical_pattern or "",
           "include": [], "exclude": []}
    site_dir.mkdir(parents=True, exist_ok=True)
    write_site_toml(site_dir, cfg)
    if not (site_dir / "inventory.csv").exists():
        write_csv_rows(site_dir / "inventory.csv", [])
    out(f"Đã tạo {site_dir / 'site.toml'}")
    out(f"  Nền tảng: {cms}; sitemap: {len(sitemaps)}; ngôn ngữ: {lang or 'chưa rõ'}")
    if fetcher.robots_blocked:
        out("  robots.txt chặn một số địa chỉ; những địa chỉ đó sẽ không được lấy.")
    if cms == "other" and not sitemaps:
        out("  Không thấy API hay sitemap. Dùng import-csv với danh sách URL xuất từ CMS.")
    out(f"Bước tiếp: python3 scripts/site_inventory.py refresh --site {site_dir.name}")
    return 0


def _sitemap_candidates(cfg: dict, fetcher: Fetcher) -> list:
    sm = list(cfg.get("sitemaps") or [])
    if not sm:
        sm = [u for u in fetcher.sitemaps_from_robots if same_site(u, cfg["base_url"])]
    return sm or [cfg["base_url"] + "/sitemap.xml"]


def scan_site(cfg: dict, fetcher: Fetcher, *, limit: Optional[int], fetch_pages: bool,
              out=print) -> tuple[list, bool, list]:
    """Return (fresh_rows, complete, notes)."""
    base = cfg["base_url"].rstrip("/")
    cms = cfg.get("cms", "other")
    lang = cfg.get("lang", "")
    per_group = limit if limit else DEFAULT_PAGE_CAP
    total_cap = DEFAULT_PAGE_CAP
    rows: list = []
    truncated = False
    notes: list = []
    structured_ok = False
    skip_hints: tuple = ()

    if cms in ("wordpress", "woocommerce"):
        r, cut, ok = wp_rows(fetcher, base, per_group, lang)
        rows += r
        truncated = truncated or cut
        structured_ok = ok
        if cms == "woocommerce":
            r, cut = woo_rows(fetcher, base, per_group, lang)
            rows += r
            truncated = truncated or cut
            structured_ok = structured_ok or bool(r)
        if not ok:
            notes.append("REST API của WordPress không trả dữ liệu, chuyển sang sitemap.")
    elif cms in ("shopify", "haravan"):
        r, cut = shop_rows(fetcher, base, cms, per_group, lang)
        rows += r
        truncated = truncated or cut
        if any(x["type"] == "product" for x in r):
            skip_hints = ("product",)
        # blog posts and pages are not in the JSON API: sitemap for those below
    elif cms == "blogger":
        r, cut = blogger_rows(fetcher, base, per_group, lang)
        rows += r
        truncated = truncated or cut
        structured_ok = bool(r)

    need_sitemap = (cms in ("shopify", "haravan")) or not structured_ok
    if need_sitemap:
        have = {norm_url(x["url"]) for x in rows}
        urls, cut = collect_sitemap_urls(fetcher, _sitemap_candidates(cfg, fetcher), base,
                                         per_group=per_group, total_cap=total_cap, skip_hints=skip_hints)
        truncated = truncated or cut
        stamp = now_iso()
        fetched = 0
        for loc, lastmod, hint in urls:
            if not url_allowed(loc, cfg.get("include", []), cfg.get("exclude", [])):
                continue
            key = norm_url(loc)
            if key in have:
                continue
            have.add(key)
            r = blank_row()
            r.update(url=clean_text(loc, 500).replace(" ", ""), lastmod=clean_text(lastmod, 40),
                     type=classify(loc, hint), lang=lang, source="sitemap", fetched_at=stamp)
            if fetch_pages and fetched < total_cap:
                try:
                    resp = fetcher.get(loc, accept="text/html")
                except FetchError:
                    resp = None
                if resp is not None and resp.status == 200:
                    fetched += 1
                    page = extract_page(resp.body.decode("utf-8", "replace"))
                    canon = page["canonical"]
                    if canon and same_site(canon, base) and norm_url(canon) != key and norm_url(canon) in have:
                        continue
                    r.update(title=page["title"], h1=page["h1"], description=page["description"],
                             price=page["price"], in_stock=page["in_stock"],
                             lang=(page["lang"][:2] or lang),
                             type=classify(loc, hint, page["og_type"], page["is_product"]))
                elif resp is not None and resp.status in (404, 410):
                    continue
            rows.append(r)
    include, exclude = cfg.get("include", []), cfg.get("exclude", [])
    rows = [clamp_row(r) for r in rows if same_site(r["url"], base) and url_allowed(r["url"], include, exclude)]
    if fetcher.robots_blocked:
        notes.append(f"robots.txt đã chặn {len(set(fetcher.robots_blocked))} địa chỉ, không lấy.")
    return rows, not truncated, notes


def cmd_refresh(args, out=print, transport=None, delay: float = REQUEST_DELAY) -> int:
    site_dir = resolve_site(args.site)
    cfg = load_site_config(site_dir)
    if "base_url" not in cfg:
        raise InventoryError("site.toml thiếu base_url.")
    fetcher = make_fetcher(cfg["base_url"], site_dir, transport, delay)
    existing = load_inventory(site_dir)
    fresh, complete, notes = scan_site(cfg, fetcher, limit=args.limit,
                                       fetch_pages=not args.no_fetch_pages, out=out)
    if not fresh and not existing:
        raise InventoryError("Không lấy được URL nào. Kiểm tra site.toml hoặc dùng import-csv.")
    merged = merge_inventory(existing, fresh, complete=complete)
    write_csv_rows(site_dir / "inventory.csv", merged)
    write_inventory_json(site_dir, merged)
    counts = type_counts(merged)
    out(f"Đã cập nhật {site_dir.name}: {len(merged)} dòng ({fetcher.requests} yêu cầu).")
    out("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    if not complete:
        out("  Chạy giới hạn --limit nên chưa đánh dấu URL nào là gone.")
    for note in notes:
        out("  " + note)
    return 0


_ALIASES = {
    "url": ("url", "link", "địa chỉ", "dia chi", "permalink"),
    "title": ("title", "tiêu đề", "tieu de", "tên", "ten", "name"),
}


def read_csv_rows_loose(path: Path) -> list:
    """Like read_csv_rows but maps common header aliases (Vietnamese too)."""
    path = Path(path)
    if not path.is_file():
        raise InventoryError(f"Không thấy file {path}.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    first = text.splitlines()[0]
    delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    header = [h.strip().lower() for h in next(reader)]
    mapping = {}
    for i, h in enumerate(header):
        for canon, names in _ALIASES.items():
            if h in names and canon not in mapping.values():
                mapping[i] = canon
        if i not in mapping and h in COLUMNS:
            mapping[i] = h
    if "url" not in mapping.values():
        raise InventoryError("File CSV cần tối thiểu cột url (và nên có title).")
    rows = []
    for rec in reader:
        row = blank_row()
        for i, cell in enumerate(rec):
            if i in mapping:
                row[mapping[i]] = cell.strip()
        if row["url"]:
            rows.append(row)
    return rows


def cmd_import_csv(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    cfg = load_site_config(site_dir)
    base = cfg["base_url"]
    incoming = read_csv_rows_loose(Path(args.file))
    rows = load_inventory(site_dir)
    index = {norm_url(r["url"]): r for r in rows}
    added = updated = skipped = 0
    stamp = now_iso()
    for inc in incoming:
        url = inc["url"].strip()
        if urllib.parse.urlparse(url).scheme not in ("http", "https") or not same_site(url, base):
            skipped += 1
            continue
        key = norm_url(url)
        cur = index.get(key)
        if cur is None:
            row = blank_row()
            for col in COLUMNS:
                if inc.get(col):
                    row[col] = clean_text(inc[col], FIELD_LIMITS[col]) if col != "url" else url
            row["type"] = row["type"] if row["type"] in TYPES else classify(url)
            row["lang"] = row["lang"] or cfg.get("lang", "")
            row["source"], row["fetched_at"] = "csv", stamp
            rows.append(clamp_row(row))
            index[key] = rows[-1]
            added += 1
        else:
            changed = False
            for col in COLUMNS:
                if col in ("url", "type", "source", "fetched_at") or not inc.get(col):
                    continue
                if not cur.get(col):  # fill blanks only, never overwrite
                    cur[col] = clean_text(inc[col], FIELD_LIMITS[col])
                    changed = True
            updated += int(changed)
    write_csv_rows(site_dir / "inventory.csv", rows)
    write_inventory_json(site_dir, rows)
    out(f"Đã nhập: thêm {added}, bổ sung {updated}, bỏ qua {skipped} (sai định dạng hoặc khác tên miền).")
    return 0


def cmd_add(args, out=print, transport=None) -> int:
    site_dir = resolve_site(args.site)
    cfg = load_site_config(site_dir)
    url = args.url.strip()
    if urllib.parse.urlparse(url).scheme not in ("http", "https") or not same_site(url, cfg["base_url"]):
        raise InventoryError("URL phải thuộc web của site này (http hoặc https).")
    row = blank_row()
    row.update(url=url, title=clean_text(args.title, FIELD_LIMITS["title"]),
               description=clean_text(args.description, FIELD_LIMITS["description"]),
               category=clean_text(args.category, FIELD_LIMITS["category"]),
               lang=cfg.get("lang", ""), source="manual", fetched_at=now_iso(),
               focus_keyword=clean_text(args.focus_keyword, FIELD_LIMITS["focus_keyword"]))
    row["type"] = args.type or classify(url)
    if args.fetch:
        fetcher = make_fetcher(cfg["base_url"], site_dir, transport)
        try:
            resp = fetcher.get(url, accept="text/html")
        except FetchError as exc:
            raise InventoryError(f"Không lấy được trang: {exc}")
        if resp.status == 200:
            page = extract_page(resp.body.decode("utf-8", "replace"))
            row["title"] = row["title"] or page["title"]
            row["h1"], row["description"] = page["h1"], row["description"] or page["description"]
            row["price"], row["in_stock"] = page["price"], page["in_stock"]
            if not args.type:
                row["type"] = classify(url, None, page["og_type"], page["is_product"])
    rows = load_inventory(site_dir)
    key = norm_url(url)
    hit = next((r for r in rows if norm_url(r["url"]) == key), None)
    if hit:
        for col in GENERATED:
            if col not in ("url", "source") and row.get(col):
                hit[col] = row[col]
        if hit.get("type") == "gone" and not args.type:
            hit["type"] = row["type"]
        verb = "Đã cập nhật"
    else:
        rows.append(clamp_row(row))
        verb = "Đã thêm"
    write_csv_rows(site_dir / "inventory.csv", rows)
    write_inventory_json(site_dir, rows)
    out(f"{verb}: {url} ({row['type']})")
    return 0


def cmd_search(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    hits = search(load_inventory(site_dir), args.query, type=args.type, top=args.top)
    if args.json:
        out(json.dumps(hits, ensure_ascii=False, indent=1))
        return 0
    if not hits:
        out("Không thấy trang nào khớp.")
        return 0
    out("| # | Loại | Tiêu đề | URL | Điểm |")
    out("| --- | --- | --- | --- | --- |")
    for i, h in enumerate(hits, 1):
        title = (h.get("title") or h.get("h1") or "").replace("|", "/")
        out(f"| {i} | {h.get('type', '')} | {title} | {h['url']} | {h['score']} |")
    return 0


def cmd_list_sites(args, out=print) -> int:
    sites = list_sites()
    if not sites:
        out(f"Chưa có web nào trong {sites_root()}. Chạy: init <địa chỉ web>")
        return 0
    for s in sites:
        cfg = load_site_config(s)
        out(f"{s.name}  ({cfg.get('cms', 'other')})  {len(load_inventory(s))} dòng")
    return 0


def cmd_status(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    cfg = load_site_config(site_dir)
    rows = load_inventory(site_dir)
    stamps = [r["fetched_at"] for r in rows if r.get("fetched_at")]
    out(f"{site_dir.name}: {cfg.get('cms')} - {cfg.get('base_url')}")
    out(f"  Tổng {len(rows)} dòng; cập nhật gần nhất: {max(stamps) if stamps else 'chưa'}")
    for kind, n in sorted(type_counts(rows).items()):
        out(f"  {kind}: {n}")
    return 0


# ---------------------------------------------------------------------------
# Planning from the inventory: gaps, stale, overlap (Phase R)
# ---------------------------------------------------------------------------

COVERAGE_THRESHOLD = 0.5
"""A category or product counts as covered when one post matches at least this
share of the target name's IDF weight (see ``coverage``). 0.5 means roughly
half of the distinctive words of the name occur in one post's title, h1,
description, focus keyword, anchors, category or URL slug."""

PRIORITY_MIN = 4
OVERLAP_THRESHOLD = 0.5
DRAFT_SUFFIXES = (".md", ".mdx")
MAX_DRAFT_BYTES = 2 * 1024 * 1024
DEFAULT_PRIORITY = 3

_STOP_TOKENS = frozenset({"va", "cua", "cho", "la", "mau", "the", "mot", "cac", "nhung"})


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in ("yes", "y", "true", "1", "x", "co")


def _usable(row: dict) -> bool:
    return row.get("type") != "gone" and not _truthy(row.get("exclude", ""))


def _priority(row: dict) -> int:
    try:
        return max(1, min(5, int(float(row.get("priority", "") or DEFAULT_PRIORITY))))
    except ValueError:
        return DEFAULT_PRIORITY


def _name_of(row: dict) -> str:
    return (row.get("title") or row.get("h1") or "").strip()


_TITLE_SPLIT = re.compile(r"\s+[/|\u2013\u2014-]\s+|\s*\|\s*")


def short_name(row: dict, max_words: int = 8) -> str:
    """The product or category name without the SEO tail of its page title
    ("Quần Jeans Loose Fit Nam / Phong Cách ... / YaMe" -> "Quần Jeans Loose
    Fit Nam"), cut to ``max_words`` words. Still only words from the row."""
    head = _TITLE_SPLIT.split(_name_of(row))[0].strip()
    return " ".join(head.split()[:max_words])


def _name_tokens(name: str) -> list:
    """Unigrams and bigrams of a name, without bare numbers or filler words,
    so a product code such as "085" or the word "màu" never decides a match."""
    out = []
    for tok in tokenize(name):
        parts = tok.split()
        if len(parts) == 1 and (tok in _STOP_TOKENS or tok.isdigit()):
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


def coverage(name_tokens: list, post_doc: dict, idf: dict) -> float:
    """IDF-weighted share of ``name_tokens`` found in one post (0..1). A token
    that no post contains keeps the largest weight, so unseen words lower the
    score of every post."""
    total = got = 0.0
    for tok in name_tokens:
        w = idf.get(tok, 0.0) or 1.0
        total += w
        if tok in post_doc:
            got += w
    return got / total if total else 0.0


def find_gaps(rows: list, *, top: int = 10, threshold: float = COVERAGE_THRESHOLD) -> dict:
    """Categories and priority>=4 products that no post matches.

    Targets come only from inventory rows (``type`` category or product, not
    gone, not excluded); nothing is invented. Posts count when they are neither
    gone nor excluded. The post body is not stored in the inventory, so a post
    is judged by title, h1, description, focus keyword, anchors, category and
    URL slug only.
    """
    posts = [r for r in rows if r.get("type") == "post" and _usable(r)]
    post_docs = [row_weights(p) for p in posts]
    idf = idf_table(post_docs)
    product_cats = Counter(_key_name(r.get("category", "")) for r in rows
                           if r.get("type") == "product" and _usable(r) and r.get("category"))
    targets = []
    for r in rows:
        if not _usable(r) or not _name_of(r):
            continue
        kind = r.get("type")
        if kind == "category":
            pass
        elif kind == "product" and _priority(r) >= PRIORITY_MIN:
            pass
        else:
            continue
        name = short_name(r)
        toks = _name_tokens(name)
        if not toks:
            continue
        best, best_url = 0.0, ""
        for p, doc in zip(posts, post_docs):
            c = coverage(toks, doc, idf)
            if c > best:
                best, best_url = c, p["url"]
        if best >= threshold:
            continue
        targets.append({
            "type": kind, "name": name, "url": r["url"], "priority": _priority(r),
            "products_in_category": product_cats.get(_key_name(name), 0) if kind == "category" else 0,
            "best_coverage": round(best, 2), "closest_post": best_url if best > 0 else "",
        })
    targets = fold_subcategories(targets)
    targets.sort(key=lambda t: (-t["priority"], -t["products_in_category"],
                                0 if t["type"] == "category" else 1, t["best_coverage"], t["name"].lower()))
    return {"posts_considered": len(posts), "threshold": threshold,
            "total_gaps": len(targets), "gaps": targets[: max(0, top)]}


def fold_subcategories(targets: list) -> list:
    """Fold a category gap whose name starts with another category gap's name
    ("Balo Camping" under "Balo") into that parent, so one broad topic does
    not crowd the list with its siblings. The parent keeps the children's
    names in ``subcategories`` and their product counts in its own count."""
    cats = [t for t in targets if t["type"] == "category"]
    keys = {id(t): _key_name(t["name"]) for t in cats}
    parent_of = {}
    for t in cats:
        best = None
        for other in cats:
            if other is t:
                continue
            k, ko = keys[id(t)], keys[id(other)]
            if ko and k != ko and k.startswith(ko + " ") and (best is None or len(ko) > len(keys[id(best)])):
                best = other
        if best is not None:
            parent_of[id(t)] = best
    def root(t):
        while id(t) in parent_of:
            t = parent_of[id(t)]
        return t
    out = []
    for t in targets:
        if id(t) in parent_of:
            r = root(t)
            r.setdefault("subcategories", []).append(t["name"])
            r["products_in_category"] = r.get("products_in_category", 0) + t.get("products_in_category", 0)
            continue
        out.append(t)
    return out


def _noun_variants(variants: list, seed: str) -> list:
    """A product or category name is a noun, so the bare "cách <noun>" intent
    variant is ungrammatical; the search people make is "cách chọn <noun>"."""
    bad = f"cách {seed}"
    return [f"cách chọn {seed}" if v == bad else v for v in variants]


def _key_name(text: str) -> str:
    return " ".join(tokenize_words(text))


def tokenize_words(text: str) -> list:
    return _WORD_RE.findall(to_ascii(normalize(text or "")).lower())


def _topic_for(gap: dict) -> str:
    name = gap["name"]
    if gap["type"] == "category":
        return f"Cách chọn {name}: hướng dẫn cho người mới"
    return f"Đánh giá {name}: có đáng mua không"


def suggest_topics(gap_result: dict, *, volumes: bool = False, variants_per_row: int = 5) -> dict:
    """Attach a topic and ``vi_keywords.build_variants`` variants to each gap;
    with ``volumes`` look the variants up once (needs a DataForSEO key)."""
    import vi_keywords  # same folder; imported late so the other commands stay light
    out = dict(gap_result)
    note = ""
    gaps = []
    for g in gap_result["gaps"]:
        g = dict(g)
        # "Dây Nịt Nam (Thắt Lưng)": nobody searches the brackets, so seed
        # with the name outside them.
        seed = " ".join(re.sub(r"\([^)]*\)", " ", g["name"]).lower().split()[:6]) or g["name"].lower()
        g["topic"] = _topic_for(g)
        g["variants"] = _noun_variants([v["keyword"] for v in vi_keywords.build_variants(seed)],
                                       seed)[:variants_per_row]
        gaps.append(g)
    if volumes:
        kws = list(dict.fromkeys(k for g in gaps for k in g["variants"]))
        vols, note = vi_keywords.fetch_volumes(kws, min(len(kws), vi_keywords.MAX_LIMIT)) if kws else ({}, "")
        for g in gaps:
            g["volumes"] = {k: vols.get(k) for k in g["variants"]} if vols else {}
    out["gaps"] = gaps
    out["volumes_note"] = note
    out["volumes_requested"] = volumes
    return out


def render_gaps(result: dict) -> str:
    lines = []
    if not result["gaps"]:
        return ("Không thấy sản phẩm hay danh mục nào chưa có bài "
                f"(đã xét {result['posts_considered']} bài, ngưỡng {result['threshold']}).")
    lines.append(f"Gợi ý chủ đề cho {len(result['gaps'])} trong {result['total_gaps']} mục chưa có bài "
                 f"(đã so với {result['posts_considered']} bài trên web).")
    lines.append("Ghi chú: danh sách bài chỉ lưu tiêu đề, mô tả, từ khoá chính và URL, không lưu nội dung "
                 "bài, nên việc khớp chỉ dựa trên các trường đó. Một bài có nhắc sản phẩm trong thân bài "
                 "mà tiêu đề không nhắc vẫn có thể bị tính là chưa có bài.")
    lines.append(f"Ngưỡng: một mục được coi là đã có bài khi một bài khớp từ {int(result['threshold'] * 100)}% "
                 "trở lên (theo trọng số IDF) các từ trong tên mục.")
    if result.get("volumes_note"):
        lines.append(result["volumes_note"])
    elif result.get("volumes_requested") is False:
        lines.append("Chưa tra lượt tìm kiếm (thêm --volumes nếu đã có khoá DataForSEO).")
    lines += ["", "| # | Loại | Sản phẩm/danh mục (có thật trên web) | Chủ đề gợi ý | Từ khoá và biến thể |",
              "| --- | --- | --- | --- | --- |"]
    for i, g in enumerate(result["gaps"], 1):
        kind = "Danh mục" if g["type"] == "category" else "Sản phẩm"
        vols = g.get("volumes") or {}
        kws = "; ".join(f"{k} ({vols[k]})" if vols.get(k) is not None else k for k in g["variants"])
        extra = f" ({g['products_in_category']} sản phẩm)" if g.get("products_in_category") else ""
        if g.get("subcategories"):
            extra += "<br>gồm: " + ", ".join(g["subcategories"]).replace("|", "/")
        lines.append(f"| {i} | {kind} | {g['name'].replace('|', '/')}{extra}<br>{g['url']} | "
                     f"{g['topic'].replace('|', '/')} | {kws} |")
    return "\n".join(lines)


def cmd_gaps(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    result = find_gaps(load_inventory(site_dir), top=args.top)
    result = suggest_topics(result, volumes=args.volumes)
    if args.json:
        out(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        out(render_gaps(result))
    return 0


# ---- stale ---------------------------------------------------------------

def parse_lastmod(value: str) -> Optional[date]:
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", value or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def drafts_dir_for(drafts: Optional[str] = None) -> Path:
    """``--drafts`` if given, else ``blog-results/`` next to the sites root
    (``workspace/sites`` -> ``workspace/blog-results``)."""
    if drafts:
        return Path(drafts).expanduser()
    return sites_root().parent / "blog-results"


_MD_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)")
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def iter_drafts(drafts: Path):
    if not drafts.is_dir():
        return
    for p in sorted(drafts.rglob("*")):
        if p.suffix.lower() in DRAFT_SUFFIXES and p.is_file() and p.name.lower() != "review.md":
            try:
                if p.stat().st_size <= MAX_DRAFT_BYTES:
                    yield p, p.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue


def gone_links_in_drafts(rows: list, drafts: Path, base_url: str = "") -> list:
    gone = {norm_url(r["url"]): r for r in rows if r.get("type") == "gone" and r.get("url")}
    found = []
    if not gone:
        return found
    for path, text in iter_drafts(drafts):
        hit = set()
        for m in list(_MD_LINK.finditer(text)) + list(_HREF.finditer(text)):
            raw = m.group(1)
            if raw.startswith("/") and not raw.startswith("//") and base_url:
                raw = urllib.parse.urljoin(base_url, raw)
            if not raw.lower().startswith(("http://", "https://")):
                continue
            key = norm_url(raw)
            if key in gone and key not in hit:
                hit.add(key)
                found.append({"draft": str(path), "url": gone[key]["url"], "title": _name_of(gone[key])})
    return found


def find_stale(rows: list, drafts: Path, base_url: str = "", *, top: int = 20,
               today: Optional[date] = None) -> dict:
    today = today or date.today()
    dated, undated = [], []
    for r in rows:
        if r.get("type") != "post" or not _usable(r):
            continue
        d = parse_lastmod(r.get("lastmod", ""))
        item = {"url": r["url"], "title": _name_of(r), "lastmod": r.get("lastmod", ""),
                "age_days": (today - d).days if d else None}
        (dated if d else undated).append((d, item))
    dated.sort(key=lambda t: (t[0], t[1]["url"]))
    undated.sort(key=lambda t: t[1]["url"])
    posts = [i for _, i in dated][: max(0, top)]
    room = max(0, top - len(posts))
    unknown = [i for _, i in undated][:room]
    return {"posts": posts, "no_lastmod": unknown,
            "no_lastmod_total": len(undated), "dated_total": len(dated),
            "gone_linked": gone_links_in_drafts(rows, drafts, base_url),
            "drafts_dir": str(drafts)}


def render_stale(res: dict) -> str:
    lines = []
    if res["posts"]:
        lines += [f"Bài cũ nhất trên web (theo ngày sửa lần cuối, lastmod; {res['dated_total']} bài có ngày). "
                  "Ngày cũ chưa chắc là nội dung lỗi thời: xem lại số liệu, giá, luật trước khi sửa.", "",
                  "| # | Bài | Sửa lần cuối | Tuổi (ngày) | URL |", "| --- | --- | --- | --- | --- |"]
        for i, p in enumerate(res["posts"], 1):
            lines.append(f"| {i} | {p['title'].replace('|', '/')} | {p['lastmod'][:10]} | {p['age_days']} | {p['url']} |")
    else:
        lines.append("Không có bài nào có ngày sửa lần cuối (lastmod) trong danh sách.")
    if res["no_lastmod_total"]:
        lines += ["", f"Chưa rõ ngày ({res['no_lastmod_total']} bài không có lastmod, xếp sau các bài có ngày, "
                  "không thể so tuổi):", "", "| Bài | Ngày | URL |", "| --- | --- | --- |"]
        for p in res["no_lastmod"]:
            lines.append(f"| {p['title'].replace('|', '/')} | không rõ ngày | {p['url']} |")
    lines.append("")
    if res["gone_linked"]:
        lines += ["Bản nháp còn dẫn tới trang đã biến mất khỏi web (type=gone), cần sửa link:", "",
                  "| Bản nháp | URL đã mất |", "| --- | --- |"]
        for g in res["gone_linked"]:
            lines.append(f"| {g['draft']} | {g['url']} |")
    else:
        lines.append(f"Không có bản nháp nào trong {res['drafts_dir']} còn link tới trang đã mất.")
    return "\n".join(lines)


def cmd_stale(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    cfg = load_site_config(site_dir)
    res = find_stale(load_inventory(site_dir), drafts_dir_for(args.drafts), cfg.get("base_url", ""),
                     top=args.top)
    out(json.dumps(res, ensure_ascii=False, indent=1) if args.json else render_stale(res))
    return 0


# ---- overlap (cannibalization, site mode) --------------------------------

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _fm_value(fm: str, *keys: str) -> str:
    for k in keys:
        m = re.search(rf"^{k}\s*:\s*(.+)$", fm, re.M | re.I)
        if m:
            return m.group(1).strip().strip("\"'")
    return ""


def draft_row(path: Path, text: str) -> Optional[dict]:
    """A pseudo inventory row for a draft, or None when it has no title."""
    m = _FM_RE.match(text)
    fm = m.group(1) if m else ""
    body = text[m.end():] if m else text
    h1 = re.search(r"^#\s+(.+)$", body, re.M)
    title = _fm_value(fm, "title") or (h1.group(1).strip() if h1 else "")
    if not title:
        return None
    return {"url": _fm_value(fm, "canonical") or f"draft:{path}", "type": "draft", "title": title,
            "h1": h1.group(1).strip() if h1 else "", "description": _fm_value(fm, "description"),
            "focus_keyword": _fm_value(fm, "focus_keyword", "primary_keyword", "keyword"),
            "path": str(path)}


def _cos(a: dict, b: dict, idf: dict) -> float:
    shared = sum(idf.get(t, 0.0) * min(a[t], b[t]) for t in a.keys() & b.keys())
    na = sum(idf.get(t, 0.0) * w for t, w in a.items())
    nb = sum(idf.get(t, 0.0) * w for t, w in b.items())
    return shared / math.sqrt(na * nb) if na > 0 and nb > 0 else 0.0


def find_overlaps(rows: list, drafts: Path, *, threshold: float = OVERLAP_THRESHOLD, top: int = 20) -> dict:
    """Pairs of posts (inventory posts and drafts together) that target the
    same thing. Uses focus keyword, title, h1, description and URL slug only;
    ``description`` weighs 1, so shared boilerplate cannot flag a pair alone."""
    items = [dict(r, origin="web") for r in rows if r.get("type") == "post" and _usable(r)]
    for path, text in iter_drafts(drafts):
        d = draft_row(path, text)
        if d:
            d["origin"] = "bản nháp"
            items.append(d)
    docs = [row_weights(r) for r in items]
    idf = idf_table(docs)
    seen_urls: set = set()
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            ua, ub = norm_url(a["url"]), norm_url(b["url"])
            if ua == ub:
                continue
            sim = _cos(docs[i], docs[j], idf)
            fa, fb = _key_name(a.get("focus_keyword", "")), _key_name(b.get("focus_keyword", ""))
            exact = bool(fa) and fa == fb
            if sim < threshold and not exact:
                continue
            level = "Nghiêm trọng" if exact or sim >= 0.8 else ("Cao" if sim >= 0.65 else "Trung bình")
            pairs.append({"a": a["url"], "a_title": _name_of(a), "a_origin": a["origin"],
                          "b": b["url"], "b_title": _name_of(b), "b_origin": b["origin"],
                          "similarity": round(sim, 2), "same_focus_keyword": exact, "severity": level})
    order = {"Nghiêm trọng": 0, "Cao": 1, "Trung bình": 2}
    pairs.sort(key=lambda p: (order[p["severity"]], -p["similarity"], p["a"]))
    return {"items": len(items), "threshold": threshold, "total_pairs": len(pairs),
            "pairs": pairs[: max(0, top)]}


def render_overlaps(res: dict) -> str:
    if not res["pairs"]:
        return (f"Không thấy cặp bài nào trùng ý định (đã so {res['items']} bài gồm bài trên web và bản nháp, "
                f"ngưỡng {res['threshold']}).")
    lines = [f"{res['total_pairs']} cặp bài có thể cạnh tranh nhau (đã so {res['items']} bài; chỉ dựa trên "
             "từ khoá chính, tiêu đề, mô tả và URL, không đọc thân bài).", "",
             "| Bài A | Bài B | Độ giống | Mức độ |", "| --- | --- | --- | --- |"]
    for p in res["pairs"]:
        lines.append(f"| {p['a_title'].replace('|', '/')} ({p['a_origin']})<br>{p['a']} | "
                     f"{p['b_title'].replace('|', '/')} ({p['b_origin']})<br>{p['b']} | "
                     f"{p['similarity']} | {p['severity']}{' (cùng từ khoá chính)' if p['same_focus_keyword'] else ''} |")
    return "\n".join(lines)


def cmd_overlap(args, out=print) -> int:
    site_dir = resolve_site(args.site)
    res = find_overlaps(load_inventory(site_dir), drafts_dir_for(args.drafts),
                        threshold=args.threshold, top=args.top)
    out(json.dumps(res, ensure_ascii=False, indent=1) if args.json else render_overlaps(res))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Nhận diện nền tảng và tạo site.toml")
    s.add_argument("url")
    s.add_argument("--brand")
    s.add_argument("--author")
    s.add_argument("--canonical-pattern", dest="canonical_pattern")
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("refresh", help="Lấy lại danh sách URL của web")
    s.add_argument("--site")
    s.add_argument("--limit", type=int, help="Tối đa số dòng mỗi nguồn (đợt thử nhanh)")
    s.add_argument("--no-fetch-pages", action="store_true", help="Chỉ đọc sitemap, không tải từng trang")

    s = sub.add_parser("import-csv", help="Nhập danh sách URL từ file CSV")
    s.add_argument("file")
    s.add_argument("--site")

    s = sub.add_parser("add", help="Thêm một URL bằng tay")
    s.add_argument("url")
    s.add_argument("--site")
    s.add_argument("--title", default="")
    s.add_argument("--description", default="")
    s.add_argument("--category", default="")
    s.add_argument("--focus-keyword", dest="focus_keyword", default="")
    s.add_argument("--type", choices=[t for t in TYPES if t != "gone"])
    s.add_argument("--fetch", action="store_true", help="Tải trang để lấy tiêu đề, mô tả, giá")

    s = sub.add_parser("search", help="Tìm trong danh sách, không phân biệt dấu")
    s.add_argument("query")
    s.add_argument("--site")
    s.add_argument("--type", choices=[t for t in TYPES if t != "gone"])
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("gaps", help="Sản phẩm và danh mục chưa có bài, kèm chủ đề gợi ý")
    s.add_argument("--site")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--volumes", action="store_true", help="Tra lượt tìm kiếm (cần khoá DataForSEO)")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("stale", help="Bài cũ nhất trên web và link tới trang đã mất trong bản nháp")
    s.add_argument("--site")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--drafts", help="Thư mục bản nháp (mặc định: blog-results/ cạnh thư mục sites)")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("overlap", help="Các cặp bài (trên web và bản nháp) có thể cạnh tranh từ khoá")
    s.add_argument("--site")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--threshold", type=float, default=OVERLAP_THRESHOLD)
    s.add_argument("--drafts")
    s.add_argument("--json", action="store_true")

    sub.add_parser("list-sites", help="Các web đã cấu hình")
    s = sub.add_parser("status", help="Số dòng theo loại và lần cập nhật gần nhất")
    s.add_argument("--site")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"init": cmd_init, "refresh": cmd_refresh, "import-csv": cmd_import_csv,
                "add": cmd_add, "search": cmd_search, "gaps": cmd_gaps, "stale": cmd_stale,
                "overlap": cmd_overlap, "list-sites": cmd_list_sites, "status": cmd_status}
    try:
        return handlers[args.cmd](args)
    except InventoryError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
