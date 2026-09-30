---
name: blog-publish
description: >
  Send a finished post from blog-results/<slug>/ to a CMS as a DRAFT and print
  the draft and edit links. WordPress REST is the main client (Application
  Password, hero uploaded as featured media, categories and tags mapped, body
  converted by blog_render). Haravan Omni and Blogger are smaller clients that
  are untested against a live account. Goes live only when the user explicitly
  says to publish; a real publish then notifies IndexNow. Runs the Gate 5 and
  Phase K compliance checks first and sends nothing if they fail.
  Use when user says "publish", "post to WordPress", "push to CMS", "send draft".
  Also use when the request is written in Vietnamese, for example "đăng bài này lên WordPress", "đăng lên web", "đẩy bài lên website", "tạo bản nháp trên WordPress", "đăng lên Haravan", "đăng lên Blogger".
user-invokable: true
argument-hint: "<blog-results/slug/> [wordpress|haravan|blogger] [--publish]"
license: MIT
---

# Blog Publish

Turns a finished draft folder into a post on the marketer's CMS. The default
is always a **draft**: nothing becomes public unless the request says so in
words such as "đăng chính thức", "cho lên sóng", "publish". "Đăng bài này lên
WordPress" alone means: create the draft and show the link.

## Workflow

1. Find the draft folder (`blog-results/<slug>/`) from the conversation. If two
   posts could match, ask one short question.
2. Run the sender. Default is WordPress:

   ```bash
   python3 scripts/publish_cms.py --draft blog-results/<slug>/
   python3 scripts/publish_cms.py --draft blog-results/<slug>/ --cms haravan
   python3 scripts/publish_cms.py --draft blog-results/<slug>/ --publish   # only when asked to go live
   ```

   `--dry-run` checks everything and sends nothing.
3. Relay the output in Vietnamese: the draft link, the edit link, and any note.
   Never paste a credential, and never ask the user to type one in chat.

## What the sender does

- Reads the markdown, converts the body with the same renderer as
  `blog_render.py` (leading H1 dropped, YMYL author box kept).
- Preflight before any request. When the folder holds the slug-matched `.md`,
  `.html` and `.pdf`, it runs the real Gate 5 (`blog_preflight.py`). Otherwise
  it checks frontmatter (`title`, `slug`, `description`, `canonical`), the hero
  image and the Phase K disclosure rules (`vi_compliance.py`; see
  `skills/blog/references/vi-compliance.md`). A post that fails is not sent.
  Tell the user, in Vietnamese, which line to fix.
- WordPress: uploads the hero as media and sets it as the featured image,
  uploads local images used in the body, maps `category`/`categories` and
  `tags` (creating missing terms), puts `description` in the excerpt, and
  creates the post with `status: draft`. A post with the same slug is updated
  instead of duplicated; a **live** post with that slug is never overwritten
  unless the user asks to update the live post (`--update-live`).
  `--seo-plugin yoast|rankmath|both` also writes the meta description into the
  plugin fields; it is off by default because it has not been tried on a real
  site.
- After a real `--publish` it calls the existing IndexNow submitter
  (`claude-seo/scripts/indexnow_submit.py`, key from `INDEXNOW_KEY` and
  `INDEXNOW_KEY_LOCATION`). Drafts never trigger it.

## Credentials

Read from the credentials file by `env_file.py`; see the CREDENTIALS guide in the hub docs folder at
the hub root for where each value comes from.

| CMS | Variables |
|---|---|
| WordPress | `WORDPRESS_URL` (https), `WORDPRESS_USER`, `WORDPRESS_APP_PASSWORD` |
| Haravan | `HARAVAN_SHOP`, `HARAVAN_ACCESS_TOKEN`, `HARAVAN_BLOG_ID`, optional `HARAVAN_BLOG_HANDLE` |
| Blogger | `BLOGGER_BLOG_ID` plus either the three OAuth values or `BLOGGER_ACCESS_TOKEN` |

If a variable is missing, the script names it (never its value). Point the user
to that guide. Requests go only to the configured site, redirects
are refused so the password cannot be replayed elsewhere, and plain `http://` is
refused except on localhost.

## Honest limits

- The WordPress client has been exercised only against a local mock server in
  `tests/test_publish_cms.py`. No live WordPress site has been tested.
- Haravan and Blogger follow the vendors' documented REST shapes and have not
  been run against a live account. Blogger cannot take a slug or a hero upload
  through its API; Haravan does not receive body images. Say so in the reply.
- WordPress core has no meta-description field; without an SEO plugin the
  description goes to the excerpt only.

## Exit codes

`0` done. `1` draft not readable. `2` blocked by preflight (nothing sent). `3`
credentials missing. `4` the CMS refused or was unreachable.
