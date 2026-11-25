"""Exa search wrapper for SITREP grounding.

Runs semantic search over the open web, constrained to the domain whitelist
of grounding/grounding-set.md. Returns Evidence items that slot
into the same list as RSS-derived evidence.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable

from .schemas import Evidence
from .whitelist import classify_url, parse_sources, whitelist_domains

log = logging.getLogger(__name__)

try:
    from exa_py import Exa
except ImportError:  # pragma: no cover
    Exa = None  # type: ignore


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").replace("www.", "").lower()
    except Exception:
        return ""


def search(
    queries: Iterable[str],
    *,
    max_results_per_query: int = 5,
    start_published: datetime | None = None,
    days_back_fallback: int = 7,
) -> list[Evidence]:
    """Run one Exa search per query and return deduped Evidence.

    start_published: explicit cutoff timestamp (UTC). If provided, used as
    Exa's `start_published_date`. Otherwise falls back to `now - days_back_fallback`.
    """
    from datetime import timedelta

    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        log.warning("exa: EXA_API_KEY not set — skipping")
        return []
    if Exa is None:
        log.warning("exa: exa_py not installed — skipping")
        return []

    whitelist_sources = parse_sources()
    domains = sorted(d for d in whitelist_domains(whitelist_sources) if d != "t.me")
    names = {(_host(s.url)): (s.name, s.tier) for s in whitelist_sources}
    if not domains:
        log.warning("exa: source domain catalog empty — skipping")
        return []

    client = Exa(api_key=api_key)
    evidence: list[Evidence] = []
    seen_urls: set[str] = set()
    now = datetime.now(timezone.utc)
    cutoff = start_published or (now - timedelta(days=days_back_fallback))
    start_iso = cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("exa: cutoff start_published_date=%s", start_iso)

    q_list = [q.strip() for q in queries if q and q.strip()]
    for q in q_list:
        try:
            resp = client.search_and_contents(
                query=q,
                type="auto",
                num_results=max_results_per_query,
                include_domains=domains,
                start_published_date=start_iso,
                text={"max_characters": 2500},
                livecrawl="fallback",
            )
        except Exception as ex:
            log.warning("exa search failed q=%r: %s", q, ex)
            continue

        results = getattr(resp, "results", []) or []
        log.info("exa: query=%r hits=%d", q, len(results))
        for r in results:
            url = getattr(r, "url", "") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            host = _host(url)
            title = (getattr(r, "title", "") or "").strip()
            text = (getattr(r, "text", "") or "").strip()
            published = None
            pub_str = getattr(r, "published_date", None)
            if pub_str:
                try:
                    published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            if not title:
                continue
            reliability, alignment = classify_url(url, whitelist_sources)
            evidence.append(
                Evidence(
                    source_name=names.get(host, (host, "wire"))[0],
                    source_tier=names.get(host, (host, "wire"))[1],
                    url=url,
                    title=title,
                    body_excerpt=text[:2500],
                    fetched_at=now,
                    published_at=published,
                    source_reliability=reliability,
                    source_alignment=alignment,
                )
            )

    log.info("exa: gathered %d evidence items across %d queries", len(evidence), len(q_list))
    return evidence
