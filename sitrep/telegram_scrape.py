"""Public Telegram channel preview scraper.

Fetches the read-only HTML preview at `https://t.me/s/<channel>` and extracts
recent posts as Evidence items. No auth, no API key — this is Telegram's own
public web preview, intended for link previews.

Only use for channels that actually expose a `/s/` preview. Some restricted
or small channels don't; those return HTTP 200 but an empty post list. Callers
should treat zero-result fetches as a non-fatal miss.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .schemas import Evidence

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_POST_BLOCK = re.compile(
    r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.DOTALL,
)
_DATA_POST = re.compile(r'data-post="([^"]+)"')
_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
_TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_STRIP = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _clean_text(raw: str) -> str:
    # <br> → newline to preserve paragraph breaks, then strip all tags.
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = _TAG_STRIP.sub("", text)
    text = html.unescape(text)
    # Collapse runs of whitespace within a line, keep newlines.
    lines = [_WHITESPACE.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def _channel_name(url: str) -> str:
    """Extract channel name from a t.me or t.me/s URL."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if parts and parts[0] == "s" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else ""


def fetch_channel(
    channel_or_url: str,
    *,
    source_name: str,
    cutoff: datetime,
    max_items: int = 15,
    client: httpx.Client | None = None,
) -> list[Evidence]:
    """Fetch recent posts from a public Telegram channel preview.

    `channel_or_url` can be a bare channel name, `https://t.me/<name>`, or
    `https://t.me/s/<name>`. Returns posts with timestamp >= cutoff, newest
    last (caller can re-sort).
    """
    channel = _channel_name(channel_or_url) if "://" in channel_or_url else channel_or_url.lstrip("@")
    if not channel:
        log.warning("telegram: empty channel from %s", channel_or_url)
        return []

    url = f"https://t.me/s/{channel}"
    owns_client = client is None
    client = client or httpx.Client(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        try:
            r = client.get(url)
            r.raise_for_status()
        except Exception as ex:
            log.warning("telegram: fetch failed %s — %s", url, ex)
            return []

        html_body = r.text
        out: list[Evidence] = []
        for block_match in _POST_BLOCK.finditer(html_body):
            block = block_match.group(1)

            post_m = _DATA_POST.search(block)
            if not post_m:
                continue
            post_ref = post_m.group(1)  # "channel/123"
            post_url = f"https://t.me/{post_ref}"

            time_m = _TIME_RE.search(block)
            if not time_m:
                continue
            try:
                # datetime attribute is ISO-8601 with timezone offset.
                dt = datetime.fromisoformat(time_m.group(1).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            except Exception:
                continue
            if dt < cutoff:
                continue

            text_m = _TEXT_RE.search(block)
            body = _clean_text(text_m.group(1)) if text_m else ""
            if not body:
                continue

            # Title: first line trimmed to ~120 chars. Excerpt: up to 900 chars.
            first_line = body.split("\n", 1)[0]
            title = first_line if len(first_line) <= 120 else first_line[:117].rstrip() + "…"
            excerpt = body[:900]

            out.append(
                Evidence(
                    source_name=source_name,
                    source_tier="telegram",
                    url=post_url,
                    title=title,
                    body_excerpt=excerpt,
                    fetched_at=datetime.now(timezone.utc),
                    published_at=dt,
                )
            )
            if len(out) >= max_items:
                break

        log.info("telegram: %s — %d posts within window", channel, len(out))
        return out
    finally:
        if owns_client:
            client.close()
