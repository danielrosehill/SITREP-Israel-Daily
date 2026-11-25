"""SITREP -> structured JSON -> Typst -> PDF. Model text is passed as data, never as Typst markup."""
from __future__ import annotations

import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT, env
from .schemas import SECTION_KEYS, SitrepOut

LABELS = {
    "iran": "Iran", "lebanon_hezbollah": "Lebanon and the North", "gaza": "Gaza", "west_bank": "West Bank",
    "multilateral": "UN and Diplomacy", "antisemitism": "Antisemitism", "world_africa": "Africa",
    "world_europe": "Europe", "world_americas": "Americas",
    "world_asia_pacific": "Asia-Pacific", "world_mena_other": "Wider Middle East",
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


def payload(s: SitrepOut, ed: dict) -> dict:
    il = s.issuedAtUtc.astimezone(ZoneInfo(env("TZ", "Asia/Jerusalem")))
    by = {x.key: x for x in s.sections}
    major = s.emergencyLevel or s.urgencyScore == 5  # the timeline only earns its space on an exceptional day
    return {
        "name": env("REPORT_NAME", "SITREP Israel"), "headline": s.title,
        "day": f"{il:%B %-d}", "date": f"{il:%A, %B %-d, %Y}",
        "bluf": [runs(x.lstrip("- ")) for x in ed["bluf"]], "picture": runs(ed["picture"]),
        "posture": s.homefrontPosture.note if s.homefrontPosture and s.homefrontPosture.tier != "routine" else None,
        "analysis": [{"heading": a["heading"], "claim": a["claim"].replace("**", ""), "body": blocks(a["body"])} for a in ed["analysis"]],
        "outlook": [{"text": runs(o["text"]), "pct": int(o["percent"])} for o in ed.get("outlook") or []],
        "fronts": [{"label": LABELS[f["key"]], "title": f["title"].replace("**", ""),
                    "bullets": [runs(b.lstrip("- ")) for b in f["bullets"]]} for f in ed["fronts"]],
        "quiet": [LABELS[k] for k in SECTION_KEYS if k not in by or by[k].body.strip().upper()[:5] == "NOSIG"],
        "watch": [runs(w) for w in ed.get("watch") or []],
        "timeline": [{"t": f"{e.utc.astimezone(il.tzinfo):%H:%M}", "label": runs(e.label)}
                     for e in sorted(s.timeline or [], key=lambda e: e.utc.timestamp())] if major else [],
        "sources": [{"name": x.name, "url": x.url} for x in s.sources] if env("PDF_SOURCES") == "true" else [],
    }


def pdf(s: SitrepOut, out: Path) -> Path:
    import typst

    from .pipeline import print_edition
    cache = out.parent / "print.json"
    if not cache.exists():
        cache.write_text(json.dumps(print_edition(s), ensure_ascii=False, indent=1))
    (out.parent / "render.json").write_text(json.dumps(payload(s, json.loads(cache.read_text())), ensure_ascii=False, indent=1))
    tpl = Path(env("TYPST_TEMPLATE", str(ROOT / "templates" / "sitrep.typ")))
    typst.compile(str(tpl), output=str(out), root="/", font_paths=[str(tpl.parent / "fonts")],
                  sys_inputs={"data": str((out.parent / "render.json").resolve())})
    return out
