#!/usr/bin/env python3
"""DataForSEO Labs wrapper for blog-cannibalization.

Endpoints:
    page_intersection  keywords where two or more URLs both rank
    ranked_keywords    all keywords one URL ranks for

Environment: DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN), DATAFORSEO_PASSWORD
Output: JSON on stdout. Credentials are never printed, logged, or echoed.

Copies the task/poll pattern for the standard queue from
claude-seo/scripts/dataforseo_merchant.py (task_post then task_get, with
exponential-backoff polling) rather than the live endpoint, since the standard
queue is materially cheaper for non-urgent lookups.

Usage:
    python3 dataforseo_labs.py ranked-keywords <url> [--location 2704] [--language vi]
    python3 dataforseo_labs.py page-intersection <url1> <url2> [...] [--location 2704]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Add scripts directory to path for sibling imports (vi_text.py lives here).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import env_file  # noqa: F401  (loads ~/.claude/.env on import)
from vi_text import normalize as vi_normalize

try:
    import requests
except ImportError:
    print(
        json.dumps({"error": "requests library required. Install with: pip install requests"}),
        file=sys.stdout,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://api.dataforseo.com/v3"

ENDPOINTS = {
    "ranked_keywords": "/dataforseo_labs/google/ranked_keywords/task_post",
    "ranked_keywords_get": "/dataforseo_labs/google/ranked_keywords/task_get/advanced",
    "page_intersection": "/dataforseo_labs/google/page_intersection/task_post",
    "page_intersection_get": "/dataforseo_labs/google/page_intersection/task_get/advanced",
}

# Names as they appear in claude-seo/scripts/dataforseo_costs.py's COST_MODEL,
# used only to look up a pre-call estimate. page_intersection has no exact
# entry there today, so it resolves through that module's own fuzzy/default
# handling rather than failing.
COST_ENDPOINTS = {
    "ranked_keywords": "dataforseo_labs_google_ranked_keywords",
    "page_intersection": "dataforseo_labs_google_domain_intersection",
}

# Local fallback estimates (USD per task), used only when the sibling
# claude-seo repository is not reachable on disk. Mirrors the per-task figure
# dataforseo_costs.py uses for Labs endpoints so the two do not quietly
# diverge in the common case.
LOCAL_COST_FALLBACK = {
    "ranked_keywords": 0.012,
    "page_intersection": 0.012,
}

# Default polling configuration (standard queue)
POLL_INITIAL_DELAY = 2.0
POLL_MAX_DELAY = 60.0
POLL_MULTIPLIER = 2.0
POLL_MAX_ATTEMPTS = 15


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _get_credentials() -> tuple[str, str]:
    """Read DataForSEO credentials from environment variables.

    Accepts either DATAFORSEO_USERNAME (the name claude-seo uses) or
    DATAFORSEO_LOGIN (the name this repository's SKILL.md has always
    documented), so a single export can serve both sibling repositories.
    """
    username = os.environ.get("DATAFORSEO_USERNAME") or os.environ.get("DATAFORSEO_LOGIN", "")
    password = os.environ.get("DATAFORSEO_PASSWORD", "")
    if not username or not password:
        print(
            "Error: set DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and "
            "DATAFORSEO_PASSWORD environment variables.",
            file=sys.stderr,
        )
        result = {
            "error": "missing_credentials",
            "message": "Set DATAFORSEO_USERNAME (or DATAFORSEO_LOGIN) and DATAFORSEO_PASSWORD.",
        }
        json.dump(result, sys.stdout, indent=2)
        sys.exit(1)
    return username, password


def _auth_header(username: str, password: str) -> dict[str, str]:
    """Build the HTTP Basic Auth header.

    Called once per command, immediately before the first request, and
    passed straight into requests.post/requests.get. The header, the
    username, and the password are never logged, printed, or included in
    any JSON this script emits.
    """
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Cost check
# ---------------------------------------------------------------------------

def _print_cost_estimate(command: str, item_count: int = 1) -> None:
    """Print an estimated cost to stderr before spending anything.

    Prefers claude-seo/scripts/dataforseo_costs.py (the shared budget model)
    when the sibling repository sits next to this one on disk. Falls back to
    a fixed local estimate when it does not, or when the import fails for
    any reason. Either way, something is always printed: a silent,
    unestimated spend is not acceptable.
    """
    endpoint_name = COST_ENDPOINTS.get(command, command)
    sibling_scripts = Path(SCRIPT_DIR).resolve().parent.parent / "claude-seo" / "scripts"
    if sibling_scripts.is_dir():
        sys.path.insert(0, str(sibling_scripts))
        try:
            import dataforseo_costs  # type: ignore

            cost = dataforseo_costs.estimate(endpoint_name, item_count)
            print(
                f"Estimated cost: ${cost:.4f} ({endpoint_name}, {item_count} item(s), "
                "claude-seo cost model)",
                file=sys.stderr,
            )
            return
        except Exception:
            pass
    fallback = LOCAL_COST_FALLBACK.get(command, 0.06)
    print(
        f"Estimated cost: ~${fallback:.4f} ({endpoint_name}; claude-seo cost model "
        "unreachable, using local fallback)",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _post_task(
    endpoint_key: str,
    payload: list[dict[str, Any]],
    headers: dict[str, str],
) -> dict[str, Any]:
    """POST a task to DataForSEO and return the response."""
    url = f"{API_BASE}{ENDPOINTS[endpoint_key]}"
    print(f"Posting task to {endpoint_key}...", file=sys.stderr)

    resp = requests.post(url, json=payload, headers=headers, timeout=30, verify=True)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status_code") != 20000:
        return {
            "error": "api_error",
            "status_code": data.get("status_code"),
            "message": data.get("status_message", "Unknown API error"),
        }
    return data


def _poll_results(
    endpoint_key: str,
    task_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Poll for task results with exponential backoff."""
    get_key = f"{endpoint_key}_get"
    url = f"{API_BASE}{ENDPOINTS[get_key]}/{task_id}"

    delay = POLL_INITIAL_DELAY
    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        print(
            f"Polling attempt {attempt}/{POLL_MAX_ATTEMPTS} "
            f"(waiting {delay:.1f}s)...",
            file=sys.stderr,
        )
        time.sleep(delay)

        resp = requests.get(url, headers=headers, timeout=30, verify=True)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status_code")
        if status == 20000:
            tasks = data.get("tasks", [])
            if tasks and tasks[0].get("status_code") == 20000:
                return data
            # Task not ready yet
            task_status = tasks[0].get("status_code") if tasks else None
            if task_status and task_status != 40601:
                # 40601 = "Task In Queue"; keep polling.
                # Any other status: return the error.
                return data

        delay = min(delay * POLL_MULTIPLIER, POLL_MAX_DELAY)

    return {
        "error": "poll_timeout",
        "message": f"Task {task_id} did not complete after {POLL_MAX_ATTEMPTS} attempts.",
    }


def _extract_task_id(response: dict[str, Any]) -> Optional[str]:
    """Extract task ID from POST response."""
    tasks = response.get("tasks", [])
    if tasks and "id" in tasks[0]:
        return tasks[0]["id"]
    return None


def _extract_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract result items from DataForSEO response envelope."""
    items = []
    for task in response.get("tasks", []):
        for result in task.get("result", []) or []:
            task_items = result.get("items")
            if task_items:
                items.extend(task_items)
    return items


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_ranked_keyword(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one ranked_keywords result item."""
    keyword_data = item.get("keyword_data") or {}
    keyword_info = keyword_data.get("keyword_info") or {}
    serp_element = item.get("ranked_serp_element") or {}
    serp_item = serp_element.get("serp_item") or {}
    return {
        "keyword": keyword_data.get("keyword", ""),
        "search_volume": keyword_info.get("search_volume"),
        "cpc": keyword_info.get("cpc"),
        "competition": keyword_info.get("competition"),
        "position": serp_item.get("rank_absolute"),
        "url": serp_item.get("url", ""),
    }


def _normalize_intersection(item: dict[str, Any], targets: list[str]) -> dict[str, Any]:
    """Normalize one page_intersection result item.

    ``positions`` maps each requested URL to its rank for this keyword, so
    the caller can compute a position gap without re-walking the raw
    response envelope.
    """
    keyword_data = item.get("keyword_data") or {}
    keyword_info = keyword_data.get("keyword_info") or {}
    intersection_result = item.get("intersection_result") or {}
    positions = {}
    for index, target in enumerate(targets, start=1):
        entry = intersection_result.get(str(index)) or {}
        positions[target] = entry.get("rank_absolute")
    return {
        "keyword": keyword_data.get("keyword", ""),
        "search_volume": keyword_info.get("search_volume"),
        "cpc": keyword_info.get("cpc"),
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_ranked_keywords(args: argparse.Namespace) -> None:
    """All keywords a single URL ranks for."""
    username, password = _get_credentials()
    headers = _auth_header(username, password)
    _print_cost_estimate("ranked_keywords", item_count=1)

    payload: dict[str, Any] = {
        "target": args.url,
        "location_code": args.location,
        "language_code": args.language,
        "load_rank_absolute": True,
        "limit": args.limit,
    }
    if args.keyword_filter:
        normalized = vi_normalize(args.keyword_filter)
        payload["filters"] = [["keyword_data.keyword", "like", f"%{normalized}%"]]

    post_resp = _post_task("ranked_keywords", [payload], headers)
    if "error" in post_resp:
        json.dump(post_resp, sys.stdout, indent=2)
        return

    task_id = _extract_task_id(post_resp)
    if not task_id:
        json.dump(
            {"error": "no_task_id", "message": "No task ID in response."},
            sys.stdout,
            indent=2,
        )
        return

    result_resp = _poll_results("ranked_keywords", task_id, headers)
    if "error" in result_resp:
        json.dump(result_resp, sys.stdout, indent=2)
        return

    items = _extract_items(result_resp)
    normalized_items = [_normalize_ranked_keyword(item) for item in items]

    output = {
        "status": "success",
        "endpoint": "ranked_keywords",
        "target": args.url,
        "location_code": args.location,
        "language_code": args.language,
        "total_keywords": len(normalized_items),
        "keywords": normalized_items,
    }
    json.dump(output, sys.stdout, indent=2)


def cmd_page_intersection(args: argparse.Namespace) -> None:
    """Keywords where two or more URLs both rank."""
    username, password = _get_credentials()
    headers = _auth_header(username, password)
    _print_cost_estimate("page_intersection", item_count=1)

    pages = {str(index): url for index, url in enumerate(args.urls, start=1)}
    payload: dict[str, Any] = {
        "pages": pages,
        "location_code": args.location,
        "language_code": args.language,
        "intersections": True,
    }
    if args.keyword_filter:
        normalized = vi_normalize(args.keyword_filter)
        payload["filters"] = [["keyword_data.keyword", "like", f"%{normalized}%"]]

    post_resp = _post_task("page_intersection", [payload], headers)
    if "error" in post_resp:
        json.dump(post_resp, sys.stdout, indent=2)
        return

    task_id = _extract_task_id(post_resp)
    if not task_id:
        json.dump(
            {"error": "no_task_id", "message": "No task ID in response."},
            sys.stdout,
            indent=2,
        )
        return

    result_resp = _poll_results("page_intersection", task_id, headers)
    if "error" in result_resp:
        json.dump(result_resp, sys.stdout, indent=2)
        return

    items = _extract_items(result_resp)
    normalized_items = [_normalize_intersection(item, args.urls) for item in items]

    output = {
        "status": "success",
        "endpoint": "page_intersection",
        "targets": args.urls,
        "location_code": args.location,
        "language_code": args.language,
        "total_overlapping_keywords": len(normalized_items),
        "keywords": normalized_items,
    }
    json.dump(output, sys.stdout, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch DataForSEO Labs data for blog-cannibalization"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument(
            "--location", type=int, default=2704, help="Location code (default: 2704 = Vietnam)"
        )
        p.add_argument(
            "--language", default="vi", help="Language code (default: vi)"
        )
        p.add_argument(
            "--keyword-filter",
            dest="keyword_filter",
            help="Optional keyword substring filter, NFC-normalized before use",
        )

    p_ranked = sub.add_parser("ranked-keywords", help="All keywords a single URL ranks for")
    p_ranked.add_argument("url", help="Target URL")
    p_ranked.add_argument(
        "--limit", type=int, default=100, help="Max keywords to return (default: 100)"
    )
    add_common(p_ranked)

    p_intersection = sub.add_parser(
        "page-intersection", help="Keywords where two or more URLs both rank"
    )
    p_intersection.add_argument("urls", nargs="+", help="Two or more target URLs")
    add_common(p_intersection)

    args = parser.parse_args()

    if args.command == "page-intersection" and len(args.urls) < 2:
        json.dump(
            {
                "error": "invalid_arguments",
                "message": "page-intersection requires at least 2 URLs.",
            },
            sys.stdout,
            indent=2,
        )
        sys.exit(1)

    dispatch = {
        "ranked-keywords": cmd_ranked_keywords,
        "page-intersection": cmd_page_intersection,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
