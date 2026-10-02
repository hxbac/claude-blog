#!/usr/bin/env python3
"""Send a finished post from a draft folder to a CMS. Draft by default.

Usage:
    python3 scripts/publish_cms.py --draft blog-results/<slug>/ [--cms wordpress|haravan|blogger]
                                   [--publish] [--dry-run] [--json]

A post is created as a DRAFT unless ``--publish`` is passed. ``--publish`` is
the only path to a live post and the only path that calls IndexNow.

Order of work, and a failure at any step sends nothing:

1. read the draft markdown and convert the body with ``blog_render``;
2. preflight: Gate 5 when the draft has its .md/.html/.pdf set, otherwise the
   frontmatter, hero and Phase K compliance checks (always run);
3. credentials from the credentials file (``env_file``); missing ones are
   named, never their values;
4. create the post through the chosen client;
5. after a successful LIVE publish only (never a draft, never ``--dry-run``), when
   the post's canonical host is a configured client site, add the URL to that
   site's inventory (``site_inventory.py add``) and print the old posts that
   should link to it (``internal_links.py reverse``). A failure in this step is
   reported on stderr and never fails the publish; the live site is not edited.

Credentials are read from the environment that ``env_file`` fills. They are
never printed, never logged, never written to the workspace, and the HTTP
layer does not follow redirects so an Authorization header cannot be replayed
to another host.

Clients: ``WordPressClient`` (REST, tested against a local mock server only),
``HaravanClient`` and ``BloggerClient`` (documented REST shapes, untested
against a live account).
"""

from __future__ import annotations

import argparse
import base64
import html as html_lib
import json
import mimetypes
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import env_file  # noqa: E402,F401  (loads the credentials file)
import blog_render  # noqa: E402
from vi_text import slugify as _slugify  # noqa: E402

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
HTTP_TIMEOUT = 30


class PublishError(Exception):
    """A step failed. The message is safe to show: it never carries a secret."""


# ---------------------------------------------------------------------------
# Post model
# ---------------------------------------------------------------------------

@dataclass
class Post:
    title: str
    slug: str
    description: str
    html: str
    lang: str = "vi"
    author: str = ""
    canonical: str = ""
    tags: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    hero: Optional[Path] = None
    hero_alt: str = ""
    #: src attribute in the body -> file on disk (inside the draft folder)
    local_images: dict = field(default_factory=dict)


@dataclass
class Result:
    provider: str
    post_id: str
    status: str            # "draft" or "publish"
    url: str
    edit_url: str
    notes: list = field(default_factory=list)


def _as_list(value: Any) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        items = text.split(",")
    return [str(i).strip().strip("'\"") for i in items if str(i).strip().strip("'\"")]


def _find_markdown(draft: Path, slug: Optional[str]) -> Path:
    mds = sorted(p for p in draft.glob("*.md") if p.name != "review.md" and not p.is_symlink())
    if slug:
        mds = [p for p in mds if p.stem == slug]
    if not mds:
        raise PublishError("Không tìm thấy file .md của bài trong thư mục " + draft.name)
    if len(mds) > 1:
        names = ", ".join(p.stem for p in mds)
        raise PublishError(f"Có nhiều bài trong thư mục ({names}); hãy chỉ rõ bằng --slug")
    return mds[0]


def load_post(draft: Path, slug: Optional[str] = None) -> tuple[Post, Path, dict]:
    """Build a Post from a draft folder using the shared renderer's parser."""
    md_path = _find_markdown(draft, slug)
    raw = blog_render._read_md_safely(md_path)
    fm, body = blog_render._parse_frontmatter(raw)
    body_html = blog_render._markdown_to_html(body)
    body_html = re.sub(r"\A\s*<h1\b[^>]*>.*?</h1>\s*", "", body_html, count=1, flags=re.DOTALL)
    author_box, _text = blog_render._author_box(fm)
    body_html = body_html + ("\n" + author_box if author_box else "")

    title = str(fm.get("title") or md_path.stem)
    hero_name = blog_render._detect_hero_filename(draft)
    hero = draft / hero_name
    if not hero.is_file() or hero.is_symlink():
        hero = None

    local: dict = {}
    root = draft.resolve()
    for src in re.findall(r'<img\b[^>]*?\bsrc="([^"]+)"', body_html):
        if re.match(r"^[a-z][a-z0-9+.-]*:", src, re.I) or src.startswith("//"):
            continue
        target = (root / urllib.parse.unquote(src)).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if target.suffix.lower() in IMAGE_EXTS and target.is_file() and not target.is_symlink():
            local[src] = target
    if hero is not None:
        local.pop(hero_name, None)

    categories = _as_list(fm.get("categories") or fm.get("category"))
    post = Post(
        title=title,
        slug=str(fm.get("slug") or _slugify(title)),
        description=str(fm.get("description") or ""),
        html=body_html,
        lang=str(fm.get("lang") or "vi"),
        author=str(fm.get("author") or ""),
        canonical=str(fm.get("canonical") or ""),
        tags=_as_list(fm.get("tags")),
        categories=categories,
        hero=hero,
        hero_alt=str(fm.get("og_image_alt") or title),
        local_images=local,
    )
    return post, md_path, fm


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(draft: Path, md_path: Path, post: Post) -> tuple[list, list, str]:
    """Return (violations, warnings, mode). A violation blocks sending.

    Gate 5 runs when the draft holds the slug-matched .md, .html and .pdf set.
    Otherwise (a draft that was never rendered) the checks Gate 5 can make from
    the source run instead. The Phase K compliance check runs in both modes.
    """
    violations: list = []
    warnings: list = []
    stem = md_path.stem
    have_set = all((draft / f"{stem}.{ext}").is_file() for ext in ("html", "pdf"))
    if have_set:
        import blog_preflight
        result = blog_preflight.gate_5_asset_link_integrity(draft, slug=stem)
        violations.extend(result.get("violations", []))
        warnings.extend(result.get("warnings", []))
        return violations, warnings, "gate5"

    warnings.append(
        "Chưa có đủ bản .html và .pdf đã dựng, nên chưa chạy được Gate 5 đầy đủ; "
        "đã chạy phần kiểm tra từ nguồn (frontmatter, ảnh hero, tuân thủ)."
    )
    for key, value in (("title", post.title), ("slug", post.slug),
                       ("description", post.description), ("canonical", post.canonical)):
        if not value:
            violations.append(f"Thiếu `{key}` trong frontmatter")
    if post.hero is None:
        violations.append("Thiếu ảnh hero (hero.png/jpg/webp) trong thư mục bài")
    try:
        import vi_compliance
        raw = blog_render._read_md_safely(md_path)
        fm, body = vi_compliance.parse_frontmatter(raw)
        violations.extend(f["message"] for f in vi_compliance.check(fm, body))
    except (OSError, ValueError) as exc:
        violations.append(f"Không kiểm tra được tuân thủ pháp lý: {exc}")
    return violations, warnings, "source"


# ---------------------------------------------------------------------------
# HTTP layer (stdlib, no redirects, no secrets in messages)
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _check_base_url(url: str, what: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise PublishError(f"{what} không phải địa chỉ hợp lệ")
    if parsed.scheme != "https" and host not in LOOPBACK_HOSTS:
        raise PublishError(f"{what} phải dùng https:// (mật khẩu sẽ bị lộ nếu gửi qua http)")
    if parsed.username or parsed.password:
        raise PublishError(f"{what} không được chứa tên đăng nhập hoặc mật khẩu")
    return url.strip().rstrip("/")


def http_request(method: str, url: str, *, headers: dict, body: Optional[bytes] = None,
                 timeout: int = HTTP_TIMEOUT) -> tuple[int, dict, Any]:
    """One HTTP call. Returns (status, headers, parsed JSON or text)."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            status, rheaders, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        status, rheaders, raw = exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise PublishError(f"Không kết nối được tới {urllib.parse.urlparse(url).netloc}: {reason}")
    text = raw.decode("utf-8", errors="replace")
    try:
        data: Any = json.loads(text) if text.strip() else None
    except ValueError:
        data = text
    if 300 <= status < 400:
        raise PublishError(
            f"Máy chủ chuyển hướng (HTTP {status}); hãy đặt địa chỉ cuối cùng vào cấu hình "
            "(thường là https:// hoặc bản có/không có www)"
        )
    return status, rheaders, data


def _api_message(data: Any) -> str:
    if isinstance(data, dict):
        msg = data.get("message") or data.get("error_description") or data.get("error") or ""
        if isinstance(msg, dict):
            msg = msg.get("message", "")
        return html_lib.unescape(str(msg))[:200]
    return ""


def _fail(what: str, status: int, data: Any) -> PublishError:
    hint = {401: "thông tin đăng nhập bị từ chối", 403: "tài khoản không đủ quyền",
            404: "không tìm thấy địa chỉ API"}.get(status, "")
    parts = [f"{what} thất bại (HTTP {status})"]
    if hint:
        parts.append(hint)
    msg = _api_message(data)
    if msg:
        parts.append(msg)
    return PublishError(": ".join(parts))


def _image_bytes(path: Path) -> tuple[bytes, str]:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise PublishError(f"Ảnh {path.name} lớn hơn 15 MB")
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return path.read_bytes(), ctype


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

class Client:
    name = ""
    required: tuple = ()

    def missing(self) -> list:
        return [v for v in self.required if not os.environ.get(v)]

    def publish(self, post: Post, live: bool) -> Result:  # pragma: no cover
        raise NotImplementedError


class WordPressClient(Client):
    """WordPress REST API v2 with an Application Password (Basic auth)."""

    name = "wordpress"
    required = ("WORDPRESS_URL", "WORDPRESS_USER", "WORDPRESS_APP_PASSWORD")

    def __init__(self, update_live: bool = False, seo_plugin: str = "none"):
        self.base = _check_base_url(os.environ["WORDPRESS_URL"], "WORDPRESS_URL")
        token = base64.b64encode(
            f"{os.environ['WORDPRESS_USER']}:{os.environ['WORDPRESS_APP_PASSWORD']}".encode("utf-8")
        ).decode("ascii")
        self._auth = {"Authorization": f"Basic {token}"}
        self.update_live = update_live
        self.seo_plugin = seo_plugin

    def _call(self, method: str, path: str, *, json_body: Any = None, raw: Optional[bytes] = None,
              headers: Optional[dict] = None) -> tuple[int, dict, Any]:
        hdrs = {"Accept": "application/json", "User-Agent": "claude-blog-publish", **self._auth}
        body = raw
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            hdrs["Content-Type"] = "application/json; charset=utf-8"
        hdrs.update(headers or {})
        return http_request(method, f"{self.base}/wp-json/wp/v2{path}", headers=hdrs, body=body)

    def _upload(self, path: Path, slug: str, alt: str, title: str) -> dict:
        data, ctype = _image_bytes(path)
        fname = f"{slug}-{path.name}"
        status, _h, resp = self._call(
            "POST", "/media", raw=data,
            headers={"Content-Type": ctype,
                     "Content-Disposition": f'attachment; filename="{fname}"'})
        if status not in (200, 201) or not isinstance(resp, dict) or "id" not in resp:
            raise _fail(f"Tải ảnh {path.name} lên", status, resp)
        self._call("POST", f"/media/{resp['id']}", json_body={"alt_text": alt, "title": title})
        return resp

    def _term_ids(self, kind: str, names: list) -> list:
        ids = []
        for name in names:
            status, _h, found = self._call(
                "GET", f"/{kind}?per_page=100&search={urllib.parse.quote(name)}")
            if status != 200 or not isinstance(found, list):
                raise _fail(f"Tra cứu {kind}", status, found)
            match = next((t for t in found
                          if html_lib.unescape(str(t.get("name", ""))).casefold() == name.casefold()), None)
            if match is None:
                status, _h, made = self._call("POST", f"/{kind}", json_body={"name": name})
                if status == 400 and isinstance(made, dict) and made.get("code") == "term_exists":
                    tid = (made.get("data") or {}).get("term_id")
                    if tid:
                        ids.append(int(tid))
                        continue
                if status not in (200, 201) or not isinstance(made, dict) or "id" not in made:
                    raise _fail(f"Tạo {kind} '{name}'", status, made)
                match = made
            ids.append(int(match["id"]))
        return ids

    def publish(self, post: Post, live: bool) -> Result:
        notes: list = []
        status, _h, existing = self._call(
            "GET", f"/posts?slug={urllib.parse.quote(post.slug)}&status=any&context=edit")
        if status != 200 or not isinstance(existing, list):
            raise _fail("Kiểm tra bài đã tồn tại", status, existing)
        current = existing[0] if existing else None
        if current and current.get("status") == "publish" and not (live or self.update_live):
            raise PublishError(
                f"Bài slug '{post.slug}' đang chạy thật trên website. Để không ghi đè bài đang sống, "
                "tôi dừng lại; nếu thật sự muốn cập nhật hãy nói rõ 'cập nhật bài đang đăng' (--update-live)."
            )

        html = post.html
        for src, path in post.local_images.items():
            media = self._upload(path, post.slug, path.stem, path.stem)
            html = html.replace(f'src="{src}"', f'src="{media["source_url"]}"')
            notes.append(f"Đã tải ảnh trong bài: {path.name}")

        body: dict = {
            "title": post.title,
            "slug": post.slug,
            "content": html,
            "excerpt": post.description,
        }
        if post.hero is not None:
            media = self._upload(post.hero, post.slug, post.hero_alt, post.title)
            body["featured_media"] = int(media["id"])
            notes.append(f"Đã tải ảnh hero: {post.hero.name}")
        if post.categories:
            body["categories"] = self._term_ids("categories", post.categories)
        if post.tags:
            body["tags"] = self._term_ids("tags", post.tags)
        if self.seo_plugin in ("yoast", "both"):
            body.setdefault("meta", {})["_yoast_wpseo_metadesc"] = post.description
        if self.seo_plugin in ("rankmath", "both"):
            body.setdefault("meta", {})["rank_math_description"] = post.description
        if live:
            body["status"] = "publish"
        elif current is None:
            body["status"] = "draft"

        path = f"/posts/{current['id']}" if current else "/posts"
        status, _h, made = self._call("POST", path, json_body=body)
        if status not in (200, 201) or not isinstance(made, dict) or "id" not in made:
            raise _fail("Tạo bài trên WordPress", status, made)
        if current:
            notes.append("Bài cùng slug đã có, đã cập nhật thay vì tạo bản trùng")
        pid = made["id"]
        return Result(
            provider="WordPress", post_id=str(pid), status=str(made.get("status", body.get("status", ""))),
            url=str(made.get("link", "")),
            edit_url=f"{self.base}/wp-admin/post.php?post={pid}&action=edit", notes=notes)


class HaravanClient(Client):
    """Haravan Omni web API, blog article create. Untested against a live shop."""

    name = "haravan"
    required = ("HARAVAN_SHOP", "HARAVAN_ACCESS_TOKEN", "HARAVAN_BLOG_ID")

    def __init__(self, **_):
        self.base = _check_base_url(os.environ.get("HARAVAN_API_BASE", "https://apis.haravan.com"),
                                    "HARAVAN_API_BASE")
        self.blog_id = re.sub(r"\D", "", os.environ["HARAVAN_BLOG_ID"])
        if not self.blog_id:
            raise PublishError("HARAVAN_BLOG_ID phải là số")
        self.shop = os.environ["HARAVAN_SHOP"].strip().replace("https://", "").rstrip("/")
        self.blog_handle = os.environ.get("HARAVAN_BLOG_HANDLE", "news").strip("/")

    def publish(self, post: Post, live: bool) -> Result:
        article: dict = {
            "title": post.title,
            "handle": post.slug,
            "body_html": post.html,
            "summary_html": post.description,
            "author": post.author,
            # Haravan blogs have no categories; they are folded into tags.
            "tags": ", ".join(dict.fromkeys(post.categories + post.tags)),
            "published": bool(live),
        }
        notes = []
        if post.hero is not None:
            data, _ctype = _image_bytes(post.hero)
            article["image"] = {"attachment": base64.b64encode(data).decode("ascii"),
                                "filename": f"{post.slug}-{post.hero.name}", "alt": post.hero_alt}
        if post.local_images:
            notes.append("Ảnh nằm trong thân bài chưa được tải lên Haravan; hãy thêm thủ công")
        headers = {"Authorization": f"Bearer {os.environ['HARAVAN_ACCESS_TOKEN']}",
                   "Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
                   "User-Agent": "claude-blog-publish"}
        status, _h, resp = http_request(
            "POST", f"{self.base}/web/blogs/{self.blog_id}/articles.json", headers=headers,
            body=json.dumps({"article": article}).encode("utf-8"))
        art = resp.get("article") if isinstance(resp, dict) else None
        if status not in (200, 201) or not isinstance(art, dict) or "id" not in art:
            raise _fail("Tạo bài trên Haravan", status, resp)
        aid = art["id"]
        handle = art.get("handle") or post.slug
        return Result(
            provider="Haravan", post_id=str(aid),
            status="publish" if art.get("published_at") or live else "draft",
            url=f"https://{self.shop}/blogs/{self.blog_handle}/{handle}",
            edit_url=f"https://{self.shop}/admin/blogs/{self.blog_id}/articles/{aid}", notes=notes)


class BloggerClient(Client):
    """Blogger API v3 posts.insert. Untested against a live blog."""

    name = "blogger"
    required = ("BLOGGER_BLOG_ID",)

    def __init__(self, **_):
        self.api = _check_base_url(os.environ.get("BLOGGER_API_BASE", "https://www.googleapis.com/blogger/v3"),
                                   "BLOGGER_API_BASE")
        self.token_url = _check_base_url(os.environ.get("BLOGGER_TOKEN_URL", "https://oauth2.googleapis.com/token"),
                                         "BLOGGER_TOKEN_URL")
        self.blog_id = re.sub(r"\D", "", os.environ.get("BLOGGER_BLOG_ID", ""))

    def missing(self) -> list:
        gone = super().missing()
        refresh = all(os.environ.get(v) for v in
                      ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"))
        if not refresh and not os.environ.get("BLOGGER_ACCESS_TOKEN"):
            gone.append("BLOGGER_REFRESH_TOKEN (cùng BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET) hoặc BLOGGER_ACCESS_TOKEN")
        return gone

    def _access_token(self) -> str:
        if all(os.environ.get(v) for v in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")):
            form = urllib.parse.urlencode({
                "client_id": os.environ["BLOGGER_CLIENT_ID"],
                "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
                "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
                "grant_type": "refresh_token"}).encode("ascii")
            status, _h, resp = http_request(
                "POST", self.token_url, body=form,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
            if status != 200 or not isinstance(resp, dict) or not resp.get("access_token"):
                raise _fail("Làm mới token Blogger", status, resp)
            return str(resp["access_token"])
        return os.environ["BLOGGER_ACCESS_TOKEN"]

    def publish(self, post: Post, live: bool) -> Result:
        if not self.blog_id:
            raise PublishError("BLOGGER_BLOG_ID phải là số")
        notes = ["Blogger tự tạo đường dẫn từ tiêu đề, không nhận slug; API cũng không có chỗ tải ảnh hero, "
                 "hãy đặt ảnh hero thủ công nếu cần"]
        query = urllib.parse.urlencode({"isDraft": "false" if live else "true"})
        payload = {"kind": "blogger#post", "title": post.title, "content": post.html,
                   "labels": list(dict.fromkeys(post.categories + post.tags))}
        headers = {"Authorization": f"Bearer {self._access_token()}",
                   "Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
                   "User-Agent": "claude-blog-publish"}
        status, _h, resp = http_request(
            "POST", f"{self.api}/blogs/{self.blog_id}/posts/?{query}", headers=headers,
            body=json.dumps(payload).encode("utf-8"))
        if status not in (200, 201) or not isinstance(resp, dict) or "id" not in resp:
            raise _fail("Tạo bài trên Blogger", status, resp)
        pid = resp["id"]
        return Result(
            provider="Blogger", post_id=str(pid),
            status="draft" if str(resp.get("status", "")).upper() == "DRAFT" or not live else "publish",
            url=str(resp.get("url", "")),
            edit_url=f"https://www.blogger.com/blog/post/edit/{self.blog_id}/{pid}", notes=notes)


CLIENTS = {"wordpress": WordPressClient, "haravan": HaravanClient, "blogger": BloggerClient}


# ---------------------------------------------------------------------------
# IndexNow (after a real publish only)
# ---------------------------------------------------------------------------

def _indexnow_script() -> Optional[Path]:
    here = Path(__file__).resolve()
    candidates = [
        os.environ.get("INDEXNOW_SCRIPT", ""),
        str(here.parents[2] / "claude-seo" / "scripts" / "indexnow_submit.py"),
        str(Path.home() / ".claude" / "skills" / "seo" / "scripts" / "indexnow_submit.py"),
        str(Path.home() / ".claude" / "scripts" / "indexnow_submit.py"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    return None


def notify_indexnow(url: str) -> str:
    """Submit one live URL to IndexNow through claude-seo's submitter.

    The key travels in the environment, never on the command line. Returns a
    Vietnamese status line; never raises, because the post is already live.
    """
    if not (os.environ.get("INDEXNOW_KEY") and os.environ.get("INDEXNOW_KEY_LOCATION")):
        return "IndexNow: bỏ qua (chưa đặt INDEXNOW_KEY và INDEXNOW_KEY_LOCATION)."
    script = _indexnow_script()
    if script is None:
        return "IndexNow: bỏ qua (không tìm thấy claude-seo/scripts/indexnow_submit.py)."
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--host", host, "--urls", url],
            capture_output=True, text=True, timeout=90, env=dict(os.environ))
    except (OSError, subprocess.SubprocessError) as exc:
        return f"IndexNow: không chạy được ({type(exc).__name__})."
    if proc.returncode == 0:
        return f"IndexNow: đã gửi {url}"
    return "IndexNow: không thành công (kiểm tra file khóa đã đặt đúng ở INDEXNOW_KEY_LOCATION chưa)."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _save_report(draft: Path, cms: str, result: Result) -> Optional[Path]:
    out = draft / f"publish-{cms}.json"
    if out.is_symlink():
        return None
    data = {"provider": result.provider, "id": result.post_id, "status": result.status,
            "url": result.url, "edit_url": result.edit_url}
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def record_in_inventory(draft: Path, md_path: Path, post: Post, fm: dict, result: Result,
                        out=print, quiet: bool = False) -> None:
    """After a successful live publish: add the new URL to the client site's
    inventory and print which old posts should link to it (Phase Q).

    Does nothing when the post is not on a configured site. A failure here is
    reported and swallowed: the post is already live, so it must never turn the
    publish into a failure. A draft on the CMS is not recorded (its URL is a
    preview, not the public page), and nothing here ever edits the live site.
    """
    try:
        import internal_links
        import site_inventory
        candidates = [u for u in (post.canonical, result.url) if u]
        site_dir = url = None
        for u in candidates:
            site_dir = internal_links.site_for_canonical(u)
            if site_dir is not None:
                url = u
                break
        if site_dir is None:
            return
        args = argparse.Namespace(
            url=url, site=str(site_dir), title=post.title, description=post.description,
            category=(post.categories[0] if post.categories else ""),
            focus_keyword=str(fm.get("focus_keyword") or fm.get("primary_keyword") or fm.get("keyword") or ""),
            type="post", fetch=False)
        site_inventory.cmd_add(args, out=(lambda *_: None))
        if quiet:
            return
        out(f"Đã thêm bài vào danh sách của web {site_dir.name}: {url}")
        site = internal_links.load_site(site_dir)
        draft_obj = internal_links.load_draft(md_path)
        info = internal_links.post_info(draft_obj, url)
        sugg = internal_links.reverse_suggestions(site, info, top=5)
        if sugg:
            out(internal_links.render_reverse(sugg, url))
    except Exception as exc:  # noqa: BLE001 - the post is already live
        print(f"Lưu ý: bài đã đăng nhưng chưa ghi được vào danh sách web ({exc}). "
              "Thêm tay bằng: python3 scripts/site_inventory.py add <địa chỉ bài>", file=sys.stderr)


def run(args: argparse.Namespace, out=print) -> int:
    draft = Path(args.draft).resolve()
    if not draft.is_dir():
        out(f"Không thấy thư mục bài: {args.draft}")
        return 1
    try:
        post, md_path, _fm = load_post(draft, args.slug)
    except (PublishError, OSError, ValueError) as exc:
        out(f"Không đọc được bài: {exc}")
        return 1

    violations, warnings, mode = preflight(draft, md_path, post)
    for w in warnings:
        out(f"Lưu ý: {w}")
    if violations:
        out("Bài CHƯA được gửi đi vì chưa qua kiểm tra trước khi đăng:")
        for v in violations:
            out(f"  - {v}")
        out("Hãy sửa các mục trên rồi nhờ tôi đăng lại.")
        return 2

    client_cls = CLIENTS[args.cms]
    if args.dry_run:
        out(f"[thử khô] Qua kiểm tra ({mode}). Sẽ tạo {'BÀI ĐANG CHẠY THẬT' if args.publish else 'bản nháp'} "
            f"trên {args.cms}: \"{post.title}\" (slug {post.slug}), {len(post.tags)} thẻ, "
            f"{len(post.categories)} chuyên mục, ảnh hero: {'có' if post.hero else 'không'}. Chưa gửi gì.")
        return 0

    probe = client_cls.__new__(client_cls)
    missing = client_cls.missing(probe)
    if missing:
        out(f"Chưa cấu hình {args.cms}. Còn thiếu trong file credentials: " + ", ".join(missing))
        out("Xem hướng dẫn lấy khóa trong docs/CREDENTIALS.md (mục Publishing to a CMS).")
        return 3

    try:
        client = client_cls(update_live=args.update_live, seo_plugin=args.seo_plugin)
        result = client.publish(post, live=args.publish)
    except PublishError as exc:
        out(f"Đăng lên {args.cms} không thành công: {exc}")
        return 4

    live = args.publish and result.status == "publish"
    if args.json:
        out(json.dumps({"provider": result.provider, "id": result.post_id, "status": result.status,
                        "url": result.url, "edit_url": result.edit_url, "notes": result.notes},
                       ensure_ascii=False))
    else:
        if live:
            out(f"Đã ĐĂNG bài lên {result.provider}.")
            out(f"Địa chỉ bài: {result.url}")
        else:
            out(f"Đã tạo BẢN NHÁP trên {result.provider}, chưa công khai.")
            out(f"Xem bản nháp: {result.url}")
        out(f"Trang sửa bài: {result.edit_url}")
        for note in result.notes:
            out(f"- {note}")
    try:
        _save_report(draft, args.cms, result)
    except OSError:
        pass
    if live:
        record_in_inventory(draft, md_path, post, _fm, result, out=out, quiet=bool(args.json))
        out(notify_indexnow(result.url))
    elif not args.json:
        out("Khi cần lên sóng, nói: \"đăng chính thức bài này\" (chạy lại với --publish).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--draft", required=True, help="Thư mục bài, ví dụ blog-results/<slug>/")
    p.add_argument("--slug", help="Chọn bài khi thư mục có nhiều file .md")
    p.add_argument("--cms", choices=sorted(CLIENTS), default="wordpress")
    p.add_argument("--publish", action="store_true",
                   help="Đăng công khai. Không có cờ này thì luôn chỉ tạo bản nháp.")
    p.add_argument("--update-live", action="store_true",
                   help="Cho phép cập nhật bài cùng slug đang chạy thật (WordPress)")
    p.add_argument("--seo-plugin", choices=["none", "yoast", "rankmath", "both"], default="none",
                   help="Ghi thêm meta description vào plugin SEO (chưa thử với site thật)")
    p.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra, không gửi gì")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[list] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
