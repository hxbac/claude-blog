"""Phase N: blog-publish against a LOCAL mock HTTP server only.

No real WordPress, Haravan or Blogger site is contacted anywhere in this file.
The mock speaks just enough of each documented REST shape to prove that the
client builds the right requests, defaults to a draft, and reports the URL.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import publish_cms

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
SECRET = "abcd efgh ijkl mnop qrst uvwx"
USER = "editor-hien"


class Mock:
    """A tiny CMS. ``routes`` decide the response; every request is recorded."""

    def __init__(self):
        self.requests: list[dict] = []
        self.posts: list[dict] = []
        self.terms = {"categories": [], "tags": []}
        self.next_id = 100
        self.redirect = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _handler(self):
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                parsed = urlparse(self.path)
                rec = {"method": self.command, "path": parsed.path, "query": parse_qs(parsed.query),
                       "headers": dict(self.headers), "raw": raw}
                ctype = self.headers.get("Content-Type", "")
                rec["json"] = json.loads(raw) if raw and "json" in ctype else None
                mock.requests.append(rec)
                if mock.redirect:
                    self.send_response(301)
                    self.send_header("Location", "http://127.0.0.1:1/elsewhere")
                    self.end_headers()
                    return
                status, body = mock.route(rec)
                out = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = _serve

        return H

    # routing
    def route(self, r):
        p, m = r["path"], r["method"]
        wp = "/wp-json/wp/v2"
        if p.startswith(wp):
            if "Authorization" not in r["headers"]:
                return 401, {"code": "rest_forbidden", "message": "Sorry, you are not allowed."}
            return self.wordpress(m, p[len(wp):], r)
        if p.startswith("/web/blogs/") and p.endswith("/articles.json"):
            return self.haravan(r)
        if p.startswith("/blogger/blogs/"):
            return self.blogger(r)
        if p == "/token":
            return 200, {"access_token": "fresh-token", "expires_in": 3599}
        return 404, {"message": "no route"}

    def wordpress(self, m, path, r):
        if path == "/media" and m == "POST":
            mid = self._new_id()
            return 201, {"id": mid, "source_url": f"{self.url}/wp-content/uploads/{mid}.png"}
        if re.fullmatch(r"/media/\d+", path):
            return 200, {"id": int(path.split("/")[-1])}
        if path.startswith("/posts") and m == "GET":
            slug = r["query"].get("slug", [""])[0]
            return 200, [p for p in self.posts if p["slug"] == slug]
        if path == "/posts" and m == "POST":
            body = r["json"]
            post = {"id": self._new_id(), "slug": body["slug"], "status": body.get("status", "draft"),
                    "link": f"{self.url}/?p={self.next_id}", "body": body}
            self.posts.append(post)
            return 201, post
        if re.fullmatch(r"/posts/\d+", path) and m == "POST":
            pid = int(path.split("/")[-1])
            post = next(p for p in self.posts if p["id"] == pid)
            post["body"] = r["json"]
            post["status"] = r["json"].get("status", post["status"])
            return 200, post
        kind = path.lstrip("/").split("?")[0]
        if kind in self.terms:
            if m == "GET":
                q = r["query"].get("search", [""])[0]
                return 200, [t for t in self.terms[kind] if q.lower() in t["name"].lower()]
            term = {"id": self._new_id(), "name": r["json"]["name"]}
            self.terms[kind].append(term)
            return 201, term
        return 404, {"message": "no route"}

    def haravan(self, r):
        if r["headers"].get("Authorization") != "Bearer hv-token":
            return 401, {"error": "invalid token"}
        art = r["json"]["article"]
        return 201, {"article": {"id": 777, "handle": art["handle"],
                                 "published_at": "2026-09-30T00:00:00Z" if art["published"] else None}}

    def blogger(self, r):
        if r["headers"].get("Authorization") != "Bearer fresh-token":
            return 401, {"error": {"message": "bad token"}}
        live = r["query"].get("isDraft") == ["false"]
        return 200, {"id": "555", "status": "LIVE" if live else "DRAFT",
                     "url": "https://demo.blogspot.com/2026/09/post.html"}


@pytest.fixture
def mock():
    m = Mock()
    yield m
    m.close()


POST_MD = """---
title: Cách chọn máy pha cà phê cho gian bếp nhỏ
slug: cach-chon-may-pha-ca-phe
description: Hướng dẫn chọn máy pha cà phê theo diện tích bếp và thói quen uống.
date: 2026-09-01
author: Nguyễn Hiền
lang: vi
canonical: https://example.vn/cach-chon-may-pha-ca-phe
tags: [may pha ca phe, gian bep nho]
category: Gia dụng
%(extra)s---

# Cách chọn máy pha cà phê cho gian bếp nhỏ

Bạn nên đo chiều rộng bàn bếp trước khi chọn máy.

![Sơ đồ đặt máy](so-do.png)

## Áp suất

Áp suất ổn định giúp ly cà phê ngon đều mỗi sáng.
"""


def make_draft(tmp_path: Path, extra: str = "", body: str | None = None) -> Path:
    draft = tmp_path / "cach-chon-may-pha-ca-phe"
    draft.mkdir()
    text = POST_MD % {"extra": extra}
    if body is not None:
        text = text.split("# Cách chọn")[0] + body
    (draft / "cach-chon-may-pha-ca-phe.md").write_text(text, encoding="utf-8")
    (draft / "hero.png").write_bytes(PNG)
    (draft / "so-do.png").write_bytes(PNG)
    return draft


@pytest.fixture
def wp_env(monkeypatch, mock):
    monkeypatch.setenv("WORDPRESS_URL", mock.url)
    monkeypatch.setenv("WORDPRESS_USER", USER)
    monkeypatch.setenv("WORDPRESS_APP_PASSWORD", SECRET)
    for name in ("INDEXNOW_KEY", "INDEXNOW_KEY_LOCATION"):
        monkeypatch.delenv(name, raising=False)
    return mock


def run_cli(argv, capsys):
    code = publish_cms.main(argv)
    out = capsys.readouterr()
    return code, out.out + out.err


def wp_posts(mock):
    return [r for r in mock.requests if r["method"] == "POST" and re.fullmatch(r"/wp-json/wp/v2/posts(/\d+)?", r["path"])]


# ---------------------------------------------------------------------------
# WordPress
# ---------------------------------------------------------------------------

def test_default_creates_a_draft_and_prints_its_url(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    code, out = run_cli(["--draft", str(draft)], capsys)
    assert code == 0, out
    (post_req,) = wp_posts(wp_env)
    body = post_req["json"]
    assert body["status"] == "draft"
    assert body["slug"] == "cach-chon-may-pha-ca-phe"
    assert body["title"].startswith("Cách chọn máy pha cà phê")
    assert body["excerpt"].startswith("Hướng dẫn chọn máy")
    assert "<h2" in body["content"] and "Áp suất" in body["content"]
    assert "<h1" not in body["content"]
    assert "BẢN NHÁP" in out
    assert f"{wp_env.url}/?p=" in out
    assert f"{wp_env.url}/wp-admin/post.php?post=" in out and "action=edit" in out
    assert (draft / "publish-wordpress.json").is_file()


def test_map_hero_categories_tags_and_body_images(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    code, _ = run_cli(["--draft", str(draft)], capsys)
    assert code == 0
    body = wp_posts(wp_env)[0]["json"]
    media = [r for r in wp_env.requests if r["path"] == "/wp-json/wp/v2/media" and r["method"] == "POST"]
    assert len(media) == 2                      # hero + the diagram in the body
    hero = media[-1]
    assert hero["raw"] == PNG
    assert "cach-chon-may-pha-ca-phe-hero.png" in hero["headers"]["Content-Disposition"]
    assert body["featured_media"] > 0
    assert "so-do.png" not in body["content"]   # rewritten to the uploaded URL
    assert "/wp-content/uploads/" in body["content"]
    assert len(body["tags"]) == 2 and len(body["categories"]) == 1
    assert {t["name"] for t in wp_env.terms["tags"]} == {"may pha ca phe", "gian bep nho"}
    assert wp_env.terms["categories"][0]["name"] == "Gia dụng"


def test_basic_auth_header_carries_the_application_password(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    run_cli(["--draft", str(draft)], capsys)
    auth = wp_env.requests[0]["headers"]["Authorization"]
    assert base64.b64decode(auth.split()[1]).decode() == f"{USER}:{SECRET}"


def test_credentials_never_printed_or_written(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    _code, out = run_cli(["--draft", str(draft), "--publish"], capsys)
    for token in (SECRET, SECRET.replace(" ", ""), base64.b64encode(f"{USER}:{SECRET}".encode()).decode()):
        assert token not in out
        for f in draft.iterdir():
            assert token.encode() not in f.read_bytes(), f.name


def test_publish_flag_goes_live_and_only_then(tmp_path, wp_env, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(publish_cms, "notify_indexnow", lambda url: calls.append(url) or "IndexNow: đã gửi")
    draft = make_draft(tmp_path)
    code, out = run_cli(["--draft", str(draft), "--publish"], capsys)
    assert code == 0, out
    assert wp_posts(wp_env)[0]["json"]["status"] == "publish"
    assert "Đã ĐĂNG" in out
    assert calls == [wp_env.posts[0]["link"]]
    assert "IndexNow: đã gửi" in out


def test_draft_never_calls_indexnow(tmp_path, wp_env, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(publish_cms, "notify_indexnow", lambda url: calls.append(url) or "x")
    run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert calls == []


def test_indexnow_runs_the_seo_submitter_with_key_in_env_not_argv(monkeypatch, tmp_path):
    script = tmp_path / "indexnow_submit.py"
    script.write_text("print('ok')\n")
    monkeypatch.setenv("INDEXNOW_SCRIPT", str(script))
    monkeypatch.setenv("INDEXNOW_KEY", "0123456789abcdef")
    monkeypatch.setenv("INDEXNOW_KEY_LOCATION", "https://example.vn/0123456789abcdef.txt")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw["env"]
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(publish_cms.subprocess, "run", fake_run)
    msg = publish_cms.notify_indexnow("https://example.vn/bai-moi")
    assert "đã gửi" in msg
    assert "--host" in seen["cmd"] and "example.vn" in seen["cmd"]
    assert "0123456789abcdef" not in " ".join(seen["cmd"])
    assert seen["env"]["INDEXNOW_KEY"] == "0123456789abcdef"


def test_indexnow_skipped_without_key(monkeypatch):
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    assert "bỏ qua" in publish_cms.notify_indexnow("https://example.vn/x")


def test_compliance_failure_sends_nothing(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path, extra="sponsored: true\n")
    code, out = run_cli(["--draft", str(draft), "--publish"], capsys)
    assert code == 2
    assert "CHƯA được gửi" in out and "sponsored" in out
    assert wp_env.requests == []


def test_missing_hero_blocks(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    (draft / "hero.png").unlink()
    code, out = run_cli(["--draft", str(draft)], capsys)
    assert code == 2 and "hero" in out
    assert wp_env.requests == []


def test_missing_credentials_are_named_not_valued(tmp_path, mock, monkeypatch, capsys):
    for name in ("WORDPRESS_URL", "WORDPRESS_USER", "WORDPRESS_APP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    code, out = run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert code == 3
    assert "WORDPRESS_URL" in out and "docs/CREDENTIALS.md" in out
    assert mock.requests == []


def test_dry_run_sends_nothing(tmp_path, wp_env, capsys):
    code, out = run_cli(["--draft", str(make_draft(tmp_path)), "--dry-run"], capsys)
    assert code == 0 and "Chưa gửi gì" in out and "bản nháp" in out
    assert wp_env.requests == []


def test_existing_draft_is_updated_not_duplicated(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    run_cli(["--draft", str(draft)], capsys)
    code, out = run_cli(["--draft", str(draft)], capsys)
    assert code == 0
    assert len(wp_env.posts) == 1
    assert "đã cập nhật thay vì tạo bản trùng" in out


def test_live_post_is_not_overwritten_without_consent(tmp_path, wp_env, capsys):
    draft = make_draft(tmp_path)
    run_cli(["--draft", str(draft), "--publish"], capsys)
    before = len(wp_posts(wp_env))
    code, out = run_cli(["--draft", str(draft)], capsys)
    assert code == 4 and "đang chạy thật" in out
    assert len(wp_posts(wp_env)) == before
    code, _ = run_cli(["--draft", str(draft), "--update-live"], capsys)
    assert code == 0 and wp_env.posts[0]["status"] == "publish"


def test_redirect_is_refused_and_never_followed(tmp_path, wp_env, capsys):
    wp_env.redirect = True
    code, out = run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert code == 4 and "chuyển hướng" in out
    assert len(wp_env.requests) == 1


def test_plain_http_to_a_real_host_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WORDPRESS_URL", "http://blog.example.vn")
    monkeypatch.setenv("WORDPRESS_USER", USER)
    monkeypatch.setenv("WORDPRESS_APP_PASSWORD", SECRET)
    code, out = run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert code == 4 and "https://" in out
    assert SECRET not in out


def test_rejected_credentials_give_a_readable_error(tmp_path, wp_env, monkeypatch, capsys):
    monkeypatch.setattr(wp_env, "route", lambda r: (401, {"code": "incorrect_password", "message": "Sai mật khẩu"}))
    code, out = run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert code == 4 and "HTTP 401" in out and "Sai mật khẩu" in out
    assert SECRET not in out


def test_seo_plugin_meta_is_opt_in(tmp_path, wp_env, capsys):
    run_cli(["--draft", str(make_draft(tmp_path))], capsys)
    assert "meta" not in wp_posts(wp_env)[0]["json"]


# ---------------------------------------------------------------------------
# Haravan and Blogger (documented shapes, mock only)
# ---------------------------------------------------------------------------

def test_haravan_draft_and_live(tmp_path, mock, monkeypatch, capsys):
    monkeypatch.setenv("HARAVAN_API_BASE", mock.url)
    monkeypatch.setenv("HARAVAN_SHOP", "demo.myharavan.com")
    monkeypatch.setenv("HARAVAN_ACCESS_TOKEN", "hv-token")
    monkeypatch.setenv("HARAVAN_BLOG_ID", "42")
    monkeypatch.setenv("HARAVAN_BLOG_HANDLE", "tin-tuc")
    draft = make_draft(tmp_path)
    code, out = run_cli(["--draft", str(draft), "--cms", "haravan"], capsys)
    assert code == 0, out
    art = mock.requests[0]["json"]["article"]
    assert mock.requests[0]["path"] == "/web/blogs/42/articles.json"
    assert art["published"] is False and art["handle"] == "cach-chon-may-pha-ca-phe"
    assert "Gia dụng" in art["tags"] and "may pha ca phe" in art["tags"]
    assert art["image"]["attachment"] == base64.b64encode(PNG).decode()
    assert "https://demo.myharavan.com/blogs/tin-tuc/cach-chon-may-pha-ca-phe" in out
    assert "hv-token" not in out
    code, out = run_cli(["--draft", str(draft), "--cms", "haravan", "--publish"], capsys)
    assert code == 0 and mock.requests[-1]["json"]["article"]["published"] is True


def test_blogger_refreshes_token_and_defaults_to_draft(tmp_path, mock, monkeypatch, capsys):
    monkeypatch.setenv("BLOGGER_API_BASE", mock.url + "/blogger")
    monkeypatch.setenv("BLOGGER_TOKEN_URL", mock.url + "/token")
    monkeypatch.setenv("BLOGGER_BLOG_ID", "999")
    monkeypatch.setenv("BLOGGER_CLIENT_ID", "cid")
    monkeypatch.setenv("BLOGGER_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("BLOGGER_REFRESH_TOKEN", "rtoken")
    monkeypatch.delenv("BLOGGER_ACCESS_TOKEN", raising=False)
    code, out = run_cli(["--draft", str(make_draft(tmp_path)), "--cms", "blogger"], capsys)
    assert code == 0, out
    insert = mock.requests[-1]
    assert insert["query"]["isDraft"] == ["true"]
    assert insert["json"]["labels"][0] == "Gia dụng"
    assert "blogger.com/blog/post/edit/999/555" in out
    for secret in ("csecret", "rtoken", "fresh-token"):
        assert secret not in out


def test_blogger_missing_credentials_named(tmp_path, monkeypatch, capsys):
    for n in ("BLOGGER_BLOG_ID", "BLOGGER_ACCESS_TOKEN", "BLOGGER_REFRESH_TOKEN",
              "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET"):
        monkeypatch.delenv(n, raising=False)
    code, out = run_cli(["--draft", str(make_draft(tmp_path)), "--cms", "blogger"], capsys)
    assert code == 3 and "BLOGGER_BLOG_ID" in out


# ---------------------------------------------------------------------------
# Preflight uses the real Gate 5 when the rendered set exists
# ---------------------------------------------------------------------------

def test_gate5_runs_when_html_and_pdf_exist(tmp_path, wp_env, capsys, monkeypatch):
    draft = make_draft(tmp_path)
    (draft / "cach-chon-may-pha-ca-phe.html").write_text("<html></html>")
    (draft / "cach-chon-may-pha-ca-phe.pdf").write_bytes(b"%PDF-1.4")
    import blog_preflight
    seen = {}

    def fake_gate5(d, slug=None, **kw):
        seen["slug"] = slug
        return {"violations": ["JSON-LD wordCount lệch"], "warnings": []}

    monkeypatch.setattr(blog_preflight, "gate_5_asset_link_integrity", fake_gate5)
    code, out = run_cli(["--draft", str(draft), "--publish"], capsys)
    assert code == 2 and "wordCount" in out
    assert seen["slug"] == "cach-chon-may-pha-ca-phe"
    assert wp_env.requests == []
