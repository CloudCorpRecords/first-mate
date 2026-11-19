"""Context.dev adapter: give the agent the web with one API.

Optional path, only when CONTEXT_DEV_API_KEY is set:
  POST {CONTEXT_DEV_BASE_URL}/v1/web/scrape with the URL, asking for
  markdown. Base URL defaults to https://api.context.dev and can be
  changed in .env. No key or credits are needed for the demo, this is
  an optional upgrade only.

Default path, no key or the call fails:
  Fetch the page directly with urllib and pull out plain text with a
  simple HTML to text pass. No third party sees the link list.

Every result is labelled with the source that was actually used, so a
demo never claims a live call that did not happen.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape

from .config import Config


@dataclass
class LinkResult:
    url: str
    title: str
    excerpt: str
    source: str  # "Context.dev" or "Direct fetch (fallback)" or "Not fetched"
    ok: bool
    # How each route was actually used, for the All accesses record.
    # Each is "used", "failed", or "not used".
    context_dev_attempt: str = "not used"
    direct_attempt: str = "not used"
    accessed_at: str = ""


def _html_to_text(html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = _clean(title_match.group(1)) if title_match else ""
    body = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return title, _clean(unescape(body))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _excerpt(text: str, limit: int = 400) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def fetch_via_context_dev(url: str, config: Config) -> LinkResult:
    payload = json.dumps(
        {"url": url, "formats": {"markdown": True}}
    ).encode("utf-8")
    endpoint = config.context_dev_base_url.rstrip("/") + "/v1/web/scrape"
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.context_dev_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.fetch_timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    # Be liberal about response shape, sponsors vary. Look for markdown
    # or text in the common places, fall back to a stringified body.
    markdown = ""
    if isinstance(data, dict):
        for key in ("markdown", "content", "text"):
            if isinstance(data.get(key), str) and data[key]:
                markdown = data[key]
                break
        if not markdown and isinstance(data.get("data"), dict):
            inner = data["data"]
            for key in ("markdown", "content", "text"):
                if isinstance(inner.get(key), str) and inner[key]:
                    markdown = inner[key]
                    break
    if not markdown:
        markdown = _clean(json.dumps(data))[:2000]
    return LinkResult(
        url=url,
        title="",
        excerpt=_excerpt(markdown),
        source="Context.dev",
        ok=True,
    )


def fetch_direct(url: str, config: Config) -> LinkResult:
    req = urllib.request.Request(
        url, headers={"User-Agent": "FirstMate/0.1 (boat hackathon demo)"}
    )
    with urllib.request.urlopen(req, timeout=config.fetch_timeout) as resp:
        raw = resp.read(300_000).decode("utf-8", "replace")
        content_type = resp.headers.get_content_type()
    if content_type == "text/html" or "<html" in raw[:500].lower():
        title, text = _html_to_text(raw)
    else:
        title, text = "", _clean(raw)
    return LinkResult(
        url=url,
        title=title,
        excerpt=_excerpt(text),
        source="Direct fetch (fallback)",
        ok=True,
    )


def _stamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def fetch_link(url: str, config: Config) -> LinkResult:
    """Fetch one link, Context.dev first if configured, fallback second."""
    context_attempt = "not used"
    if config.context_dev_configured:
        try:
            result = fetch_via_context_dev(url, config)
            result.context_dev_attempt = "used"
            result.direct_attempt = "not used"
            result.accessed_at = _stamp()
            return result
        except Exception:
            context_attempt = "failed"  # fall through to the direct fetch
    try:
        result = fetch_direct(url, config)
        result.context_dev_attempt = context_attempt
        result.direct_attempt = "used"
        result.accessed_at = _stamp()
        return result
    except Exception as exc:  # offline, blocked, bad URL, timeout
        return LinkResult(
            url=url,
            title="",
            excerpt=f"Could not fetch this link here ({type(exc).__name__}). "
            "The link is kept in the Ship Log so the team can open it.",
            source="Not fetched",
            ok=False,
            context_dev_attempt=context_attempt,
            direct_attempt="failed",
            accessed_at=_stamp(),
        )


def fetch_links(urls: list[str], config: Config) -> list[LinkResult]:
    """Fetch links in parallel so a slow link does not stall the demo."""
    if len(urls) <= 1:
        return [fetch_link(url, config) for url in urls]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(4, len(urls))) as pool:
        return list(pool.map(lambda url: fetch_link(url, config), urls))
