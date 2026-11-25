"""triage -> research -> informational -> (follow-up) -> analyst -> score -> newsletter -> audio script."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import exa, guards, research
from .config import data_dir, env, prompt
from .feeds import fetch_all
from .llm import complete_json, complete_text
from .schemas import SECTION_KEYS, Evidence, SitrepOut, TriageResult
from .whitelist import classify_url, parse_sources

log = logging.getLogger(__name__)
EVIDENCE_LIMIT = 120

TRIAGE_FEEDS = [
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("Haaretz", "https://www.haaretz.com/srv/haaretz-latest-headlines"),
    ("Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Tasnim (IRGC-aligned)", "https://www.tasnimnews.com/en/rss/feed/0/7/0/"),
    ("Al-Manar (Hezbollah)", "https://english.almanar.com.lb/rss"),
    ("CENTCOM", "https://www.centcom.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=808&isdashboardselected=0&max=20"),
    ("Long War Journal", "https://www.longwarjournal.org/tags/israel/feed"),
    ("Iran International", "https://www.iranintl.com/en/rss.xml"),
]


def recent_sitreps(n: int = 7) -> list[dict]:
    """Earlier runs on disk: the archive that replaced the database."""
    out = []
    for p in sorted((data_dir() / "runs").glob("*/sitrep.json"), reverse=True)[:n]:
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            log.warning("unreadable archive file %s", p)
    return out


def _entry_dt(e):
    for k in ("published_parsed", "updated_parsed"):
        if getattr(e, k, None):
            return datetime(*getattr(e, k)[:6], tzinfo=timezone.utc)


def _prior_block(priors: list[dict], limit: int = 5) -> str:
    if not priors:
        return "(no prior SITREPs in context)"
    return "\n\n".join(
        f"[{i}] issued {p.get('issuedAtUtc', '?')} — {p.get('title', '')}\n    BLUF: {str(p.get('bluf', ''))[:300]}"
        for i, p in enumerate(priors[:limit], 1))


def triage(state: dict) -> TriageResult:
    sources, rows = parse_sources(), []
    fetched = fetch_all([u for _, u in TRIAGE_FEEDS])
    for name, url in TRIAGE_FEEDS:
        rel, align = classify_url(url, sources)
        for e in fetched[url].entries[:15]:
            dt = _entry_dt(e)
            if dt and dt < state["coverage_from_utc"]:
                continue
            rows.append((dt, f"- [{name} · {rel}/{align}] ({dt.isoformat() if dt else '?'}) "
                             f"{getattr(e, 'title', '')}  {getattr(e, 'summary', '')[:160]}", rel))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    rows.sort(key=lambda r: r[0] or epoch, reverse=True)
    user = (f"Window: last {state['coverage_hours']:g} hours, {len(rows)} headlines.\n\n"
            f"PRIOR SITREP:\n{_prior_block(state['prior_sitreps'], 1)}\n\n" + "\n".join(r[1] for r in rows[:120]))
    if state["focus"]:
        user += f"\n\nOPERATOR FOCUS (internal): {state['focus']}"
    t = TriageResult.model_validate(complete_json(
        prompt("triage"), user, max_tokens=1200, temperature=0.2, validate=TriageResult.model_validate))
    if t.urgency == "flash" and not any(r[2] in ("trusted", "mainstream") for r in rows):
        t = t.model_copy(update={"urgency": "priority"})
    log.info("triage: %s %s", t.urgency, t.hot_topics)
    return t


def _ev_block(evidence: list[Evidence]) -> str:
    out = []
    for i, ev in enumerate(evidence[:EVIDENCE_LIMIT], 1):
        n = ev.dup_count
        sat = f"SAT×{n}" if n >= 4 else (f"FEW×{n}" if n >= 2 else "SOLO")
        out.append(f"[{i:03d}] {sat} [{ev.source_reliability}/{ev.source_alignment}] {ev.source_name} "
                   f"({ev.source_tier}) — {ev.title}\n      url: {ev.url}\n"
                   f"      published: {ev.published_at.isoformat() if ev.published_at else '—'}\n"
                   f"      excerpt: {re.sub(r'<[^>]+>', ' ', ev.body_excerpt)[:600]}")
    return "\n\n".join(out)


def _check_info(d: dict) -> None:
    if len(d.get("highlights") or []) != 3 or not d.get("sections") or not d.get("bluf"):
        raise ValueError("informational output is missing bluf, sections or exactly 3 highlights")


def _check_analyst(d: dict) -> None:
    for k in ("osintIndicators", "analysisPoints", "predictionsStable", "predictionsEscalatory"):
        if len(d.get(k) or []) != 3:
            raise ValueError(f"{k} must have exactly 3 items")


def _text(v) -> str:
    return "\n".join(f"- {str(x).lstrip('- ')}" for x in v) if isinstance(v, list) else str(v or "")


def informational(state: dict, evidence: list[Evidence]) -> dict:
    tri = state["triage"]
    focus = (f"\nOPERATOR FOCUS (internal — never mention in output): {state['focus']}\n" if state["focus"] else "")
    user = (f"WINDOW:\n  now_utc: {state['now'].isoformat()}\n  coverage_from_utc: {state['coverage_from_utc'].isoformat()}\n"
            f"  coverage_hours: {state['coverage_hours']}\n  cadence: daily\n  short_delta: False\n"
            f"  urgency: {tri.urgency}\n  hot_topics: {tri.hot_topics}\n{focus}"
            f"\nPRIOR SITREPS:\n{_prior_block(state['prior_sitreps'])}\n"
            f"\nEVIDENCE ({len(evidence)} items, newest first):\n\n{_ev_block(evidence)}\n")
    return complete_json(prompt("informational"), user, max_tokens=14000, validate=_check_info)


def _check_print(d: dict) -> None:
    if not d.get("bluf") or not d.get("fronts") or len(d.get("analysis") or []) != 3 or not d.get("picture"):
        raise ValueError("print edition is missing bluf, picture, fronts or 3 analysis points")
    for a in d["analysis"]:
        a["heading"], a["claim"], a["body"]
    for f in d["fronts"]:
        if f["key"] not in SECTION_KEYS or not f["title"] or not f["bullets"]:
            raise ValueError("bad front in print edition")
    for o in d.get("outlook") or []:
        o["text"], int(o["percent"])


def print_edition(s: SitrepOut) -> dict:
    """Condensed copy for the PDF. Everything in it comes from the full SITREP."""
    return complete_json(prompt("print"), "FINAL SITREP:\n\n" + s.model_dump_json(
        include={"title", "bluf", "highlights", "topline", "sections", "analysisPoints", "predictionsStable",
                 "predictionsEscalatory", "osintIndicators"}), max_tokens=6000, temperature=0.3, validate=_check_print)


def run(hours: float = 24, focus: str = "", urls: list[str] | None = None) -> tuple[SitrepOut, list[Evidence], str]:
    now = datetime.now(timezone.utc)
    state = {"now": now, "coverage_from_utc": now - timedelta(hours=hours), "coverage_hours": hours,
             "prior_sitreps": recent_sitreps(), "focus": focus.strip(), "manual_urls": urls or []}
    state["triage"] = triage(state)
    evidence: list[Evidence] = research.run(state)["evidence"]
    minimum = int(env("MIN_EVIDENCE", "10"))
    if len(evidence) < minimum:
        raise RuntimeError(f"only {len(evidence)} evidence items (minimum {minimum}); not writing a report")

    info = informational(state, evidence)
    queries = [q for q in (info.get("needs_more_research") or []) if isinstance(q, str) and q.strip()][:4]
    if queries:
        seen = {e.url for e in evidence}
        new = [e for e in exa.search(queries, max_results_per_query=4, start_published=state["coverage_from_utc"])
               if e.url not in seen]
        if new:
            # Up front: anything past EVIDENCE_LIMIT is not shown to the model.
            evidence = new + evidence
            info = informational(state, evidence)
    info.pop("needs_more_research", None)

    analysis = complete_json(
        prompt("analyst"),
        f"WINDOW:\n  short_delta: False\n  cadence: daily\n\nPRIOR SITREPS:\n{_prior_block(state['prior_sitreps'])}\n"
        f"\nINFORMATIONAL OUTPUT:\n\n{json.dumps(info, indent=1, default=str)}\n",
        max_tokens=7000, validate=_check_analyst)
    merged = {**info, **analysis}

    # Fields the code owns, whatever the model wrote.
    merged.update(issuedAtUtc=now, coverageFromUtc=state["coverage_from_utc"], cadence="daily",
                  urgency=state["triage"].urgency, bluf=_text(merged.get("bluf")), topline=_text(merged.get("topline")))
    shown = evidence[:EVIDENCE_LIMIT]
    merged["sources"] = [s for s in merged.get("sources") or [] if isinstance(s, dict) and s.get("url")]
    merged["tags"] = merged.get("tags") or []
    merged["sections"] = [s for s in merged["sections"] if s.get("key") in SECTION_KEYS]
    for s in merged["sections"]:
        s["title"], s["body"] = s.get("title") or "", _text(s.get("body")) or "NOSIG"
    sitrep = None
    optional = ("timeline", "predictionsStructured", "keyAssumptions", "sourceRefs", "locationRefs",
                "homefrontPosture", "changesSincePrior")
    for k in ("", *optional):  # a malformed optional block must not lose the day's report
        try:
            sitrep = SitrepOut.model_validate(merged)
            break
        except ValueError as ex:
            bad = {e["loc"][0] for e in ex.errors()} & set(optional) if hasattr(ex, "errors") else set()
            if not bad:
                raise
            log.warning("dropping malformed %s", bad)
            for b in bad:
                merged.pop(b)
    tz = ZoneInfo(env("TZ", "Asia/Jerusalem"))
    sitrep.title = re.sub(r"\s*\([^)]*(UTC|Edition)[^)]*\)", "", sitrep.title).strip()
    guards.apply(sitrep, shown)

    try:
        sc = complete_json(prompt("score"), "SITREP TO SCORE:\n\n" + sitrep.model_dump_json(
            include={"title", "bluf", "highlights", "topline", "sections", "homefrontPosture", "urgency"}),
            max_tokens=500, temperature=0.1)
        sitrep.urgencyScore = max(0, min(5, int(sc["score"])))
    except Exception as ex:
        log.warning("score failed: %s", ex)

    final = sitrep.model_dump_json(exclude={"sources", "sourceRefs", "locationRefs", "tags", "newsletterMarkdown"})
    sitrep.newsletterMarkdown = complete_text(prompt("newsletter"), f"FINAL SITREP:\n\n{final}", max_tokens=4000)
    script = ""
    if env("TTS_ENABLED", "true").lower() == "true":
        local = now.astimezone(tz)
        script = complete_text(prompt("audio"), f"DATE: {local:%A %-d %B %Y}\n\nFINAL SITREP:\n\n{final}", max_tokens=3000)
    return sitrep, evidence, script
