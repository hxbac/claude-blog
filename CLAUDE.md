# Claude Blog - Blog Creation & Optimization Skill

## Project Overview

This repository contains **Claude Blog**, a Tier 4 Claude Code skill for blog content
creation, optimization, and management. It follows the Agent Skills open standard and the
3-layer architecture (directive, orchestration, execution). 32 skill directories
(1 orchestrator + 31 sub-skills), 30 user-facing `/blog` commands, 5 specialized
subagents, 12 content templates, and 24 reference docs are dual-optimized for Google rankings
(2026 core and spam update timeline, E-E-A-T) and AI citations (GEO/AEO). Includes FLOW framework
integration, semantic topic-cluster planning + execution, multilingual publishing (Pro Hub
Challenge v1.7.0), BRAND.md/VOICE.md/DISCOURSE.md project-root context auto-load (v1.8.0,
fenced via `scripts/load_untrusted_root.py` with CSPRNG nonces, v1.8.3+), CI-enforced
prose hygiene via `scripts/lint_prose.py` (v1.8.4+), and the 5-gate Blog Delivery Contract
(v1.9.0, `skills/blog/references/blog-delivery-contract.md`) that runs `blog_preflight.py`
+ a BLOCKING `blog-reviewer` agent between every draft and the user.

## Architecture

```
claude-blog/
  CLAUDE.md                          # Project instructions (this file)
  docs/CONTRIBUTORS.md               # Pro Hub Challenge attribution and integration decisions
  CHANGELOG.md                       # Keep a Changelog format
  .claude-plugin/plugin.json         # Plugin manifest (v2.2.0)
  .claude-plugin/marketplace.json    # Marketplace catalog for distribution
  .mcp.example.json                  # MCP config example (tracked; .mcp.json is gitignored)
  pyproject.toml                     # Python packaging (3.11+)
  brain/                             # Vendored self-contained evidence-gated Obsidian brain; not plugin payload; tooling stays under skills/
  scripts/analyze_blog.py            # 5-category quality scoring (stdlib)
  scripts/blog_preflight.py          # 5-gate delivery contract runner (v1.9.0)
  scripts/blog_render.py             # md -> html -> pdf renderer; XSS-safe JSON-LD (v1.9.0)
  scripts/blog_hygiene.py            # Optional deterministic hygiene: lazy-load imgs + auto-TOC (v1.11.0)
  scripts/cognitive_load.py          # Per-section concept-density analyzer (v1.8.0)
  scripts/discourse_research.py      # Discourse brief synthesis from SERP JSON (v1.8.0)
  scripts/generate_hero.py           # Hero image ladder: Banana -> Gemini -> stock -> Openverse (v1.9.0)
  scripts/load_untrusted_root.py     # Code-enforced fence helper for BRAND/VOICE/DISCOURSE (v1.8.3)
  scripts/lint_prose.py              # Fence-aware prose-hygiene linter (v1.8.4; CI-enforced)
  scripts/sync_flow.py               # Pulls FLOW references (stdlib, sandboxed)
  scripts/ai_citation_score.py       # AI citation readiness heuristic, 0-100
  scripts/content_decay.py           # GSC content-decay detector: 20%+ QoQ decline (v1.10.0)
  scripts/quality_gate.py            # Pre-commit gate: block posts scoring < 70 (v1.10.0)
  scripts/style_learn.py             # Author voice-profile learner from sample posts (v1.10.0)
  scripts/consistency_check.py       # Local reference + FLOW lock validation
  scripts/dependency_smoke.py        # Offline optional-runtime initialization checks
  scripts/validate_public_release.py # Read-only public worktree validation
  skills/                            # 32 skill directories (1 orchestrator + 31 sub-skills)
    blog/SKILL.md                   # Main orchestrator, routing, scoring
      references/                   # 22 on-demand knowledge files (5 in v1.8.0, 1 in v1.9.0)
      templates/                    # 12 content templates
      scripts/                     # Python analysis scripts
    blog-write/SKILL.md            # Write new articles from scratch
    blog-rewrite/SKILL.md         # Optimize existing blog posts
    blog-analyze/SKILL.md         # 5-category 100-point scoring
    blog-brief/SKILL.md           # Detailed content briefs
    blog-outline/SKILL.md         # SERP-informed outlines
    blog-calendar/SKILL.md        # Editorial calendars
    blog-strategy/SKILL.md        # Blog positioning and planning
    blog-seo-check/SKILL.md      # Post-writing SEO validation
    blog-schema/SKILL.md          # JSON-LD schema generation
    blog-chart/SKILL.md           # Inline SVG data visualizations
    blog-repurpose/SKILL.md       # Multi-platform repurposing
    blog-geo/SKILL.md             # AI citation optimization
    blog-audit/SKILL.md           # Full-site blog health assessment
    blog-image/                    # AI image generation via Gemini
      SKILL.md                    # Image generation sub-skill
      references/                 # 3 reference docs (models, tools, prompts)
      scripts/                    # MCP setup and validation scripts
    blog-cannibalization/SKILL.md # Keyword overlap detection
    blog-factcheck/SKILL.md       # Statistics verification
    blog-persona/SKILL.md         # Writing persona management
    blog-taxonomy/SKILL.md        # CMS taxonomy management
    blog-notebooklm/               # NotebookLM source-grounded research
      SKILL.md                    # NotebookLM query sub-skill
      references/                 # 2 reference docs (commands, troubleshooting)
      scripts/                    # 10 Python scripts + requirements.txt
    blog-audio/                    # Audio narration via Gemini TTS
      SKILL.md                    # Audio generation sub-skill
      references/                 # 1 reference doc (30 voice catalog)
      scripts/                    # 5 Python scripts + requirements.txt
    blog-google/                   # Google API integration
      SKILL.md                    # Google API sub-skill (13 commands, 4 tiers)
      references/                 # 3 reference docs (auth, API, quotas)
      scripts/                    # 11 Google API scripts + venv wrapper
      assets/templates/           # 3 report templates
    blog-cluster/                  # Semantic topic-cluster planning + execution (v1.7.0)
      SKILL.md                    # Cluster planning + execute orchestrator
      references/                 # 3 ref docs (semantic clustering, architecture, execution)
    blog-flow/                     # FLOW framework prompts (v1.7.0)
      SKILL.md                    # FLOW orchestrator (find/optimize/win/prompts/sync)
      references/                 # Synced from github.com/AgriciDaniel/flow (CC BY 4.0)
    blog-multilingual/             # One-command international publishing (v1.7.0)
      SKILL.md                    # Multilingual orchestrator
    blog-translate/                # SEO-optimized translation (v1.7.0)
      SKILL.md
      references/                 # Translation rules + cultural adaptation profiles
    blog-localize/                 # Cultural deep-adaptation (v1.7.0)
      SKILL.md
    blog-locale-audit/             # Multilingual content QA (v1.7.0)
      SKILL.md
    blog-brand/SKILL.md            # BRAND.md + VOICE.md context files (v1.8.0)
    blog-discourse/SKILL.md        # Last-30-days discourse research (v1.8.0)
    blog-style/SKILL.md            # Author voice-profile learner (v1.10.0)
    blog-decay/SKILL.md            # GSC content-decay detector (v1.10.0)
  agents/                            # 5 specialized subagents
    blog-researcher.md              # Statistics and source research
    blog-writer.md                  # Content generation
    blog-seo.md                     # SEO validation
    blog-reviewer.md                # Quality scoring (no Bash, post v1.7.0 hardening)
    blog-translator.md              # Multilingual translation (no Bash, v1.7.0)
  tests/                             # 250+ pytest checks incl. delivery-contract + security suites
```

## Commands

| Command | Purpose |
|---------|---------|
| `/blog write` | Write new articles optimized for rankings + AI citations |
| `/blog rewrite` | Optimize existing posts with sourced statistics; `/blog update` aliases here |
| `/blog analyze` | 5-category 100-point scoring with evidence and style diagnostics, not authorship detection |
| `/blog brief` | Detailed content briefs with competitive analysis |
| `/blog outline` | SERP-informed outlines with heading hierarchy |
| `/blog calendar` | Editorial calendars with topic clusters |
| `/blog strategy` | Blog positioning and content planning |
| `/blog seo-check` | Post-writing SEO validation checklist |
| `/blog schema` | JSON-LD schema markup generation |
| `/blog repurpose` | Multi-platform content repurposing |
| `/blog geo` | AI citation optimization audit |
| `/blog image` | AI image generation and editing via Gemini |
| `/blog audit` | Full-site blog health assessment |
| `/blog cannibalization` | Detect keyword overlap across posts |
| `/blog factcheck` | Verify statistics against cited sources |
| `/blog persona` | Manage writing personas and voice profiles |
| `/blog taxonomy` | Tag/category CMS management |
| `/blog notebooklm` | Query NotebookLM for source-grounded research |
| `/blog audio` | Generate audio narration via Gemini TTS |
| `/blog google` | Google API data: PSI, CrUX, GSC, GA4, NLP, YouTube, Keywords |
| `/blog cluster` | Semantic topic-cluster planning + execution (v1.7.0) |
| `/blog multilingual` | Write + translate + localize + emit hreflang in one command (v1.7.0) |
| `/blog translate` | SEO-optimized translation with format preservation (v1.7.0) |
| `/blog localize` | Cultural deep-adaptation per locale (v1.7.0) |
| `/blog locale-audit` | Multilingual content QA (v1.7.0) |
| `/blog flow` | FLOW framework prompts: find, optimize, win, prompts index, sync (v1.7.0) |
| `/blog brand` | Generate BRAND.md + VOICE.md context auto-loaded by all sub-skills (v1.8.0) |
| `/blog discourse` | API-free last-30-days discourse research; produces DISCOURSE.md (v1.8.0) |
| `/blog style` | Learn author voice profile from existing posts (v1.10.0) |
| `/blog decay` | Detect content decay from GSC exports (v1.10.0) |

Internal capability: `blog-chart` generates inline SVG charts for `/blog write`
and `/blog rewrite`; it is not a top-level user command.

## Default market

All DataForSEO and Keyword Planner calls default to `location_code=2704` (Vietnam) and
`language_code="vi"`. Change only when the user names a different country.

- Province/city level: use the SERP API, not Labs. Hanoi 1028580, Ho Chi Minh City
  1028581, Da Nang 1028809. DataForSEO Labs covers Vietnam at country level only.
- `search_volume` bills **per task, not per keyword** (up to ~1000 keywords per task).
  Always batch into one call. Calling it once per keyword costs 1000x more for the
  same data.
- Prefer the standard queue over live mode unless the user says it is urgent:
  SERP $0.0006 vs $0.002, Keywords Data $0.06 vs $0.09.
- Never re-request a keyword already fetched in the current session.

## Conversational routing (no slash command required)

The primary user is a Vietnamese SEO content marketer who does not type slash
commands. They open Claude Code in this directory and describe what they want in
Vietnamese. Route from intent, and never answer with "use `/blog write`" when the
request itself is already the instruction.

Every skill description carries its Vietnamese trigger phrases, so matching
happens automatically. What this section adds is the behaviour around the match:

- **Act, do not offer.** "viết cho tôi bài về cách chọn máy pha cà phê" is a
  request to write the post, not a request for options. Invoke `blog-write`.
- **Reply in Vietnamese** when the user writes in Vietnamese, including gate
  failures and review findings. Keep English only for code, file paths, frontmatter
  keys and metric names.
- **Assume `lang: vi`** unless the user names another language. This selects the
  `vi` language profile in `analyze_blog.py`; getting it wrong silently scores the
  post against English patterns and costs roughly 30 of the 100 points.
- **A Vietnamese post needs an image key.** The keyless Openverse fallback indexes
  English metadata only, so a Vietnamese query returns nothing and Gate 2 fails on
  a missing hero. If none of `PEXELS_API_KEY`, `PIXABAY_API_KEY`,
  `UNSPLASH_ACCESS_KEY` or `GOOGLE_AI_API_KEY` is set, say so before writing rather
  than after the gate blocks.
- **Ambiguity between neighbouring skills gets one short question**, not a menu of
  31. "tối ưu bài này" could be `blog-rewrite`, `blog-seo-check` or `blog-analyze`;
  ask which outcome they want in one line.

### Project-scoped install

`link-skills.sh` symlinks `skills/*` and `agents/*` into `.claude/`, so this
checkout is the live source and nothing is copied into `~/.claude/`. Consequences
worth remembering:

- Editing a `SKILL.md` here takes effect on the next prompt. `git diff` is a
  complete audit of what the agent is allowed to read.
- Claude Code must run with this repository root as its working directory. About
  thirty skills call helpers by repository-relative path
  (`python3 scripts/blog_render.py`, `python3 skills/blog-google/scripts/run.py`);
  those resolve nowhere else.
- `.claude/settings.json` pins `CLAUDE_BLOG_SCRIPTS_DIR` and
  `CLAUDE_BLOG_LOAD_UNTRUSTED_HELPER` to absolute paths in this checkout. Without
  them the delivery-contract block falls back to `$HOME/.claude/scripts`, which does
  not exist under a project-scoped install.
- Per Claude Code precedence, a personal skill of the same name overrides the
  project one. Do not run `install.sh` while this wiring is in use, or `~/.claude/`
  wins and the audit trail stops being the thing that executes.

## Development Rules

- Keep SKILL.md files under 500 lines / 5000 tokens
- SKILL.md frontmatter: only valid fields (name, description, user-invokable, argument-hint, compatibility, license, metadata, disable-model-invocation). Do NOT use `allowed-tools`; it is not a Claude Code spec field
- New reference files should be focused and under 200 lines. Existing comprehensive references (platform-guides, schema-stack, content-templates, distribution-playbook) are exempt from this guideline
- Scripts must have docstrings, CLI interface, and JSON output
- Follow kebab-case naming for all skill directories
- Agents invoked via Task tool, never via Bash
- Python 3.11+ required; dependencies in pyproject.toml
- Test with `python3 -m pytest tests/` after changes
- Run `claude plugin validate .` before pushing plugin changes
- Run `python3 scripts/lint_prose.py` locally to catch forbidden prose chars before CI does (v1.8.4+)
- Project-root file loading (BRAND.md/VOICE.md/DISCOURSE.md): use `scripts/load_untrusted_root.py` via Bash; never hand-roll a fence (v1.8.3+)
- Plugin skills auto-discovered from `skills/` directory (do not list in plugin.json)

## Distribution

### Anthropic Official Marketplace
Submit at: claude.ai/settings/plugins/submit or platform.claude.com/plugins/submit

### Self-Hosted Marketplace
```
/plugin marketplace add AgriciDaniel/claude-blog
/plugin install claude-blog@agricidaniel-blog
```

### Standalone Install (no marketplace)
```bash
curl -fsSLo install.sh \
  https://raw.githubusercontent.com/AgriciDaniel/claude-blog/v2.2.0/install.sh
# Compare the SHA-256 digest with the value published in README.md.
CLAUDE_BLOG_REF=v2.2.0 bash ./install.sh
```

## Release Blog Post

After cutting a new release (git tag + `gh release create`), run:

```
/release-blog
```

This generates a blog post on https://claude-blog.md/blog/, handles cover image generation, SEO metadata, FAQ schema, internal linking, sitemap/llms.txt updates, and Vercel deployment.
