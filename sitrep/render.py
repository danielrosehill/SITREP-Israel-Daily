"""SITREP -> structured JSON -> Typst -> PDF. Model text is passed as data, never as Typst markup."""
from __future__ import annotations

import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT, env
from .schemas import SECTION_KEYS, SitrepOut

LABELS = {
    "iran": "Iran", "lebanon_hezbollah": "Lebanon / Northern Front", "gaza": "Gaza", "west_bank": "West Bank",
    "multilateral": "Multilateral", "antisemitism": "Antisemitism", "world_africa": "World: Africa",
    "world_europe": "World: Europe", "world_americas": "World: Americas",
    "world_asia_pacific": "World: Asia-Pacific", "world_mena_other": "World: Wider MENA",
}
_GENERIC = {"iran", "gaza", "west bank", "lebanon", "hezbollah", "lebanon / hezbollah", "lebanon/hezbollah", "multilateral",
            "antisemitism", "europe", "africa", "americas", "asia-pacific", "nosig"}
_TOK = re.compile(r"\*\*(.+?)\*\*|\[([^\]\n]{2,90})\](?!\()|\[([^\]]+)\]\([^)]+\)")


def runs(s: str) -> list[dict]:
    out, pos = [], 0
    for m in _TOK.finditer(s):
        if m.start() > pos:
            out.append({"k": "t", "v": s[pos:m.start()]})
        k, v = ("b", m[1]) if m[1] else ("c", m[2]) if m[2] else ("t", m[3])
        out.append({"k": k, "v": v})
        pos = m.end()
    if pos < len(s):
        out.append({"k": "t", "v": s[pos:]})
    return out


def blocks(md: str) -> list[dict]:
    out: list[dict] = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            if out and out[-1]["k"] == "p":
                out.append({"k": "gap"})
            continue
        h = re.fullmatch(r"(?:#+\s*(.+)|\*\*([^*]+)\*\*:?)", line)
        b = re.match(r"[-*•]\s+(.*)", line)
        if h:
            out.append({"k": "h", "v": (h[1] or h[2]).strip("* ")})
        elif b:
            out.append({"k": "li", "n": 1 if raw.startswith(("  ", "\t")) else 0, "r": runs(b[1])})
        elif out and out[-1]["k"] in ("p", "li") and (out[-1]["k"] == "p" or raw.startswith(" ")):
            out[-1]["r"] += [{"k": "t", "v": " "}] + runs(line)
        else:
            out.append({"k": "p", "r": runs(line)})
    return [b for b in out if b["k"] != "gap"]


def _pred(s: str) -> dict:
    m = re.search(r"\s*\[confidence:\s*([\d.]+)\]\s*$", s)
    return {"text": runs(s[:m.start()] if m else s), "conf": round(float(m[1]) * 100) if m else None}


def source_columns(s: SitrepOut) -> list:
    by: dict[str, list[str]] = {}
    for x in s.sources:
        by.setdefault(x.name, []).append(x.url)
    groups = [{"name": n, "urls": u} for n, u in by.items()]
    weight = lambda g: 1.6 + sum(1 + (len(u) > 75) for u in g["urls"])  # roughly lines
    cols, load = [[], []], [0.0, 0.0]
    for g in sorted(groups, key=weight, reverse=True):
        i = load.index(min(load))
        cols[i].append(g)
        load[i] += weight(g)
    return cols if s.sources else []


def payload(s: SitrepOut) -> dict:
    tz = ZoneInfo(env("TZ", "Asia/Jerusalem"))
    il, utc = s.issuedAtUtc.astimezone(tz), s.issuedAtUtc
    by = {x.key: x for x in s.sections}
    live = [k for k in SECTION_KEYS if k in by and by[k].body.strip().upper()[:5] != "NOSIG"]
    return {
        "name": env("REPORT_NAME", "SITREP ISRAEL"),
        "title": s.title, "bluf": blocks(s.bluf), "highlights": [runs(h) for h in s.highlights],
        "topline": blocks(s.topline), "urgency": s.urgency.upper(), "score": s.urgencyScore,
        "date": f"{il:%A %-d %B %Y}", "dtg": f"{utc:%d%H%MZ %b %y}".upper(),
        "local": f"{il:%H:%M}", "utc": f"{utc:%H:%M}", "ref": f"ISR-{il:%y%m%d}-{il:%H%M}",
        "from": f"{s.coverageFromUtc.astimezone(tz):%d %b %H:%M}", "to": f"{il:%d %b %H:%M}",
        "posture": {"tier": s.homefrontPosture.tier.upper(), "note": s.homefrontPosture.note} if s.homefrontPosture else None,
        "sections": [{"label": LABELS[k], "title": "" if by[k].title.lower() in _GENERIC else by[k].title, "body": blocks(by[k].body)} for k in live],
        "quiet": [LABELS[k] for k in SECTION_KEYS if k not in live],
        "timeline": [{"t": f"{e.utc.astimezone(tz):%d %b %H:%M}", "label": runs(e.label), "front": LABELS.get(e.front, e.front)}
                     for e in sorted(s.timeline or [], key=lambda e: e.utc.timestamp())],
        "analysis": [{"heading": a.heading, "body": blocks(a.body)} for a in s.analysisPoints or []],
        "stable": [_pred(p) for p in s.predictionsStable or []],
        "escalatory": [_pred(p) for p in s.predictionsEscalatory or []],
        "assumptions": [{"text": runs(a.text), "falsifier": runs(a.falsifier)} for a in s.keyAssumptions or []],
        "indicators": [runs(i) for i in s.osintIndicators],
        "sources": source_columns(s),
        "model": env("LLM_MODEL", "deepseek/deepseek-v4.1-flash"),
    }


def pdf(s: SitrepOut, out: Path) -> Path:
    import typst
    (out.parent / "render.json").write_text(json.dumps(payload(s), ensure_ascii=False, indent=1))
    tpl = Path(env("TYPST_TEMPLATE", str(ROOT / "templates" / "sitrep.typ")))
    typst.compile(str(tpl), output=str(out), root="/",
                  sys_inputs={"data": str((out.parent / "render.json").resolve())})
    return out
