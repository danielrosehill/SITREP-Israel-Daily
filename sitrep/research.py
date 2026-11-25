"""Node 2 — Research.

Pulls recent items from whitelisted RSS feeds, scoped to the urgency level
set by triage. No LLM calls; pure retrieval + whitelist gating.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from . import exa, telegram_scrape
from .feeds import fetch_all
from .schemas import Evidence
from .whitelist import Source, assert_whitelisted, classify_url, parse_sources

log = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(
    r"""<meta\s+[^>]*?(?:name|property)\s*=\s*["'](?P<key>[^"']+)["'][^>]*?content\s*=\s*["'](?P<val>[^"']*)["']""",
    re.IGNORECASE,
)


def _extract_meta(body: str) -> tuple[str, str]:
    """Return (title, description). Empty strings if not found."""
    title = ""
    m = _TITLE_RE.search(body)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())

    descs: dict[str, str] = {}
    for m in _META_RE.finditer(body):
        key = m.group("key").lower()
        if key in {"og:title", "twitter:title"} and not title:
            title = html.unescape(m.group("val").strip())
        if key in {"og:description", "twitter:description", "description"}:
            descs.setdefault(key, html.unescape(m.group("val").strip()))
    desc = descs.get("og:description") or descs.get("twitter:description") or descs.get("description") or ""
    return title, desc[:900]


def _fetch_manual(urls: list[str], all_sources: list[Source]) -> list[Evidence]:
    out: list[Evidence] = []
    if not urls:
        return out
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        for raw in urls:
            url = raw.strip()
            if not url:
                continue
            host = urlparse(url).hostname or "manual"
            title = ""
            desc = ""
            try:
                r = client.get(url)
                r.raise_for_status()
                title, desc = _extract_meta(r.text)
                log.info("manual: fetched %s — %s", url, (title or url)[:80])
            except Exception as ex:
                log.warning("manual: fetch failed %s — %s (including URL as bare evidence)", url, ex)
            reliability, alignment = classify_url(url, all_sources)
            out.append(
                Evidence(
                    source_name=host,
                    source_tier="manual",
                    url=url,
                    title=title or url,
                    body_excerpt=desc or f"User-submitted URL (fetch failed or blocked). Cite from {host}.",
                    fetched_at=datetime.now(timezone.utc),
                    published_at=None,
                    source_reliability=reliability,
                    source_alignment=alignment,
                )
            )
    return out


def _items_per_feed(urgency: str) -> int:
    return {"flash": 15, "priority": 10, "routine": 8, "background": 5}.get(urgency, 8)


def _items_per_analysis_feed(urgency: str) -> int:
    """Analysis-tier feeds (ISW, INSS, FDD, ICG, Long War Journal) often bury
    secondary developments inside long pieces. Pull more per feed so the writer
    sees the breadth, not just the lead."""
    return {"flash": 20, "priority": 15, "routine": 12, "background": 8}.get(urgency, 12)


def _exa_results_per_query(urgency: str) -> int:
    return {"flash": 6, "priority": 5, "routine": 4, "background": 3}.get(urgency, 4)


def _select(urgency: str, all_sources: list[Source]) -> list[Source]:
    # "primary-adversarial" (IRNA/Tasnim/Al-Manar/Al-Masirah/Iran MFA) is included
    # at every urgency level — we need to see what the axis is claiming — but
    # downstream prompts flag these as propaganda so the writer triangulates.
    if urgency == "flash":
        tiers = {"primary", "primary-adversarial", "osint", "wire"}
    elif urgency == "priority":
        tiers = {"primary", "primary-adversarial", "osint", "wire", "analysis"}
    else:
        tiers = {"primary", "primary-adversarial", "wire", "osint", "analysis", "dissident"}
    return [s for s in all_sources if s.tier in tiers and s.is_rss]


def _select_telegram(urgency: str, all_sources: list[Source]) -> list[Source]:
    # Telegram channels run at all urgency levels — they're real-time and
    # inexpensive to poll. Caller caps per-channel items via _telegram_per_channel.
    return [s for s in all_sources if s.tier == "telegram" and s.is_telegram]


def _telegram_per_channel(urgency: str) -> int:
    return {"flash": 10, "priority": 8, "routine": 5, "background": 3}.get(urgency, 5)


def run(state: dict) -> dict:
    triage = state["triage"]
    urgency = triage.urgency
    per = _items_per_feed(urgency)
    now = state.get("now") or datetime.now(timezone.utc)
    cutoff = state.get("coverage_from_utc") or (now - timedelta(hours=24))
    hours = round((now - cutoff).total_seconds() / 3600)

    all_sources = parse_sources()
    feeds = _select(urgency, all_sources)
    log.info("research: urgency=%s window=%dh feeds=%d", urgency, hours, len(feeds))

    def _entry_dt(e) -> datetime | None:
        for key in ("published_parsed", "updated_parsed"):
            if getattr(e, key, None):
                return datetime(*getattr(e, key)[:6], tzinfo=timezone.utc)
        return None

    analysis_per = _items_per_analysis_feed(urgency)
    fetched = fetch_all([s.url for s in feeds])
    evidence: list[Evidence] = []
    for s in feeds:
        try:
            assert_whitelisted(s.url, all_sources)
            parsed = fetched[s.url]
            # Sort newest-first so "first N" = "newest N" regardless of feed order.
            entries = sorted(
                parsed.entries,
                key=lambda e: _entry_dt(e) or datetime(1970, 1, 1, tzinfo=timezone.utc),
                reverse=True,
            )
            count = 0
            feed_cap = analysis_per if s.tier == "analysis" else per
            for e in entries:
                if count >= feed_cap:
                    break
                dt = _entry_dt(e)
                if dt and dt < cutoff:
                    continue
                url = getattr(e, "link", "").strip()
                if not url:
                    continue
                try:
                    assert_whitelisted(url, all_sources)
                except ValueError:
                    continue
                title = getattr(e, "title", "").strip()
                summary = getattr(e, "summary", "")[:1500].strip()
                if not title:
                    continue
                evidence.append(
                    Evidence(
                        source_name=s.name,
                        source_tier=s.tier,
                        url=url,
                        title=title,
                        body_excerpt=summary,
                        fetched_at=datetime.now(timezone.utc),
                        published_at=dt,
                        source_reliability=s.reliability,
                        source_alignment=s.alignment,
                    )
                )
                count += 1
        except Exception as ex:
            log.warning("research feed failed: %s — %s", s.name, ex)

    log.info("research (rss): gathered %d evidence items (coverage=%dh)", len(evidence), hours)

    # Telegram channels — public t.me/s/<channel> HTML preview scrape.
    tg_sources = _select_telegram(urgency, all_sources)
    if tg_sources:
        per_channel = _telegram_per_channel(urgency)
        seen = {e.url for e in evidence}
        tg_added = 0
        for s in tg_sources:
            try:
                posts = telegram_scrape.fetch_channel(
                    s.url,
                    source_name=s.name,
                    cutoff=cutoff,
                    max_items=per_channel,
                )
                for ev in posts:
                    if ev.url in seen:
                        continue
                    seen.add(ev.url)
                    # telegram_scrape doesn't know the Source — backfill from whitelist.
                    ev.source_reliability = s.reliability
                    ev.source_alignment = s.alignment
                    evidence.append(ev)
                    tg_added += 1
            except Exception as ex:
                log.warning("telegram channel failed: %s — %s", s.name, ex)
        log.info("research (telegram): +%d posts across %d channels", tg_added, len(tg_sources))

    # Manual URLs — user-submitted, bypass whitelist + coverage window.
    manual_urls = [u for u in (state.get("manual_urls") or []) if u.strip()]
    if manual_urls:
        seen = {e.url for e in evidence}
        manual_evidence = _fetch_manual(manual_urls, all_sources)
        added = 0
        for ev in manual_evidence:
            if ev.url in seen:
                continue
            seen.add(ev.url)
            evidence.append(ev)
            added += 1
        log.info("research (manual): +%d user-submitted items", added)

    # Second pass — Exa semantic search per hot topic, constrained to whitelisted domains.
    hot = [t for t in (triage.hot_topics or []) if t.strip()]
    if hot:
        exa_evidence = exa.search(
            hot,
            max_results_per_query=_exa_results_per_query(urgency),
            start_published=cutoff,
        )
        seen = {e.url for e in evidence}
        merged_new = 0
        for ev in exa_evidence:
            if ev.url in seen:
                continue
            seen.add(ev.url)
            evidence.append(ev)
            merged_new += 1
        log.info("research (exa): +%d new items (total=%d)", merged_new, len(evidence))
    else:
        log.info("research: no hot_topics — skipping Exa pass")

    # Near-dedup: collapse items with identical normalised titles, keeping
    # the one from the highest-reliability source. Cuts wire-syndication
    # noise (Reuters → AP → TOI reprints of the same story).
    evidence = _dedup_by_title(evidence)

    # Final ordering: newest-first so the writer's evidence block is recency-ranked.
    # Items without a published_at are demoted to the bottom (they can't be
    # freshness-ranked, and we don't want them displacing timestamped items).
    _EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
    evidence.sort(
        key=lambda ev: ev.published_at or _EPOCH,
        reverse=True,
    )

    log.info("research: final evidence count after dedup = %d", len(evidence))
    return {**state, "evidence": evidence}


_STOPWORDS = {"the", "a", "an", "of", "on", "in", "to", "for", "and", "with", "at", "by", "from", "as"}

_RELIABILITY_RANK = {"trusted": 0, "mainstream": 1, "caution": 2, "propaganda": 3}


def _norm_title(title: str) -> str:
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", title.lower()).split() if w and w not in _STOPWORDS]
    return " ".join(words[:6])


def _dedup_by_title(evidence: list[Evidence]) -> list[Evidence]:
    best: dict[str, Evidence] = {}
    counts: dict[str, int] = {}
    for ev in evidence:
        key = _norm_title(ev.title)
        if not key:
            # Un-normaliseable titles: keep by URL to avoid merging unrelated blanks.
            key = f"__url__{ev.url}"
        counts[key] = counts.get(key, 0) + 1
        cur = best.get(key)
        if cur is None:
            best[key] = ev
            continue
        # Prefer higher reliability, then newer published_at.
        cur_rank = _RELIABILITY_RANK.get(cur.source_reliability, 99)
        new_rank = _RELIABILITY_RANK.get(ev.source_reliability, 99)
        if new_rank < cur_rank:
            best[key] = ev
        elif new_rank == cur_rank:
            cur_dt = cur.published_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
            new_dt = ev.published_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
            if new_dt > cur_dt:
                best[key] = ev
    # Stamp dup_count on the survivor so the writer can see saturation.
    for key, ev in best.items():
        ev.dup_count = counts.get(key, 1)
    deduped = list(best.values())
    dropped = len(evidence) - len(deduped)
    if dropped > 0:
        saturated = sum(1 for ev in deduped if ev.dup_count >= 4)
        singletons = sum(1 for ev in deduped if ev.dup_count == 1)
        log.info(
            "research: dedup dropped %d near-duplicate titles (saturated=%d, singletons=%d)",
            dropped, saturated, singletons,
        )
    return deduped
