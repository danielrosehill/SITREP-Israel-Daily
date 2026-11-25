"""Canonical SITREP terminology + post-write style normaliser.

The writer LLM occasionally borrows surface forms from the source material it
quotes — e.g. "Judea and Samaria" from Israeli right-wing outlets, "Tzahal"
from Hebrew sources, "the Zionist regime" from Iranian state media. The
SITREP voice is editorially neutral: every published run uses one canonical
term per concept, regardless of the source's preferred framing.

This module is the single source of truth for that mapping. It is consumed by:
  * The writer system prompt (rendered into a readable terminology block).
  * The post-write linter (`apply_style_to_sitrep`) which rewrites stray
    variants to their canonical form before the SitrepOut is published.

Variant renderings (e.g. an Israeli-Hebrew framing layer that swaps "West
Bank" → "Judea and Samaria" at read time) belong in the *render* layer of the
website, not here. This file only defines the canonical surface.
"""

from __future__ import annotations

import re
from typing import Iterable

# Canonical → list of variant surface forms (case-insensitive whole-word).
# Keep the canonical form first; every entry on the right is a banned variant
# that gets rewritten to the canonical at lint time.
CANONICAL_TERMS: dict[str, list[str]] = {
    # --- Geography ---
    "West Bank": [
        "Judea and Samaria",
        "Judaea and Samaria",
        "Judea & Samaria",
        "Yehuda and Shomron",
        "Yehuda v'Shomron",
    ],
    "Gaza Strip": [
        # "the Strip" looks tempting but is too ambiguous — leave alone.
    ],
    "Temple Mount / Haram al-Sharif": [
        # Either side alone is editorial; SITREP uses the dual form on first
        # mention. We don't auto-rewrite here — too context-sensitive — but the
        # styleguide reminds the writer.
    ],

    # --- Forces / armed groups ---
    "IDF": [
        "Tzahal",
        "Zahal",
        "Israeli Defence Forces",  # spelled-out variant; canonical is the acronym
        "Israeli Defense Forces",
    ],
    "Hezbollah": [
        "Hizbullah",
        "Hizballah",
        "Hizbollah",
        "Party of God",
        "the Party of God",
    ],
    "Hamas": [
        # "the Resistance" only in proxy contexts — too ambiguous to auto-rewrite.
    ],
    "Houthis": [
        "Ansar Allah",  # canonical form is "Houthis" with "(Ansar Allah)" on first mention
        "Houthi rebels",
    ],
    "IRGC": [
        "Revolutionary Guards",
        "Iranian Revolutionary Guards",
        "Islamic Revolutionary Guards Corps",  # spelled out — acronym is canonical
        "Pasdaran",
    ],

    # --- Political framings to neutralise ---
    "Israel": [
        "the Zionist regime",
        "the Zionist entity",
        "the occupation",  # editorial; standalone uses are flagged
    ],
    "Iran": [
        "the Islamic Republic",  # acceptable in some contexts; canonicalised for consistency
    ],
    "Israeli citizens": [
        "settlers",
    ],
    "Israeli citizen": [
        "settler",
    ],

    # --- Verbs to neutralise (propaganda framing) ---
    # "Storm/ed/ing" is the classic loaded verb in Al-Aqsa / settlement
    # coverage. The SITREP voice never uses it; canonical is "enter/ed/ing".
    # Bare "storm" (noun: weather; verb: third-person rare) is left alone.
    "entered": ["stormed"],
    "entering": ["storming"],
    "enters": ["storms"],

    # --- Time/date wording ---
    # (intentionally empty — handled by _enforce_title_parenthetical etc.)
}


def _compile_rules() -> list[tuple[re.Pattern[str], str]]:
    """Compile one alternation pattern per canonical, with variants ordered
    longest-first so a more specific match (e.g. "Iranian Revolutionary
    Guards") wins over a shorter superstring ("Revolutionary Guards").
    """
    rules: list[tuple[re.Pattern[str], str]] = []
    for canonical, variants in CANONICAL_TERMS.items():
        if not variants:
            continue
        ordered = sorted(set(variants), key=len, reverse=True)
        # Whole-word, case-insensitive. Escape regex metas; allow flexible
        # whitespace inside multi-word variants (e.g. "Judea  and Samaria").
        alts = [re.escape(v).replace(r"\ ", r"\s+") for v in ordered]
        pat = re.compile(rf"(?i)\b(?:{'|'.join(alts)})\b")
        rules.append((pat, canonical))
    return rules


_RULES = _compile_rules()


def normalize_text(text: str) -> tuple[str, list[str]]:
    """Apply canonical-term rewrites to a free-text string.

    Returns the rewritten text plus a list of variants that fired (for
    logging). Citations inside square brackets `[Source Name]` are left alone
    so we don't mangle a source's own name (e.g. an outlet literally called
    "Judea and Samaria News").
    """
    if not text:
        return text, []

    # Mask citation brackets so rewrites don't touch source names.
    masked: list[str] = []

    def _mask(m: re.Match[str]) -> str:
        masked.append(m.group(0))
        return f"\x00CITE{len(masked) - 1}\x00"

    body = re.sub(r"\[[^\]]+\]", _mask, text)

    fired: list[str] = []
    for pat, canon in _RULES:
        def _replace(m: re.Match[str]) -> str:
            # Preserve sentence-initial capitalisation: if the matched variant
            # started with an uppercase letter, capitalise the canonical's
            # first character. Otherwise leave the canonical as-defined (the
            # canonical table already uses the editorially correct case for
            # acronyms like "IDF" and "IRGC").
            return canon[0].upper() + canon[1:] if m.group(0)[:1].isupper() else canon
        if pat.search(body):
            body = pat.sub(_replace, body)
            fired.append(canon)

    # Fix "a/an" agreement when a substitution flipped the following word's
    # initial sound (e.g. "a settler" → "a Israeli citizen" → "an Israeli
    # citizen"). Only touches indefinite articles that immediately precede a
    # rewritten phrase; doesn't try to be a general copyeditor.
    # Only the "a → an before vowel" direction. The reverse ("an → a") is
    # too risky — "an honest mistake", "an hour" etc. would get broken.
    if fired:
        body = re.sub(r"\b([Aa])\s+([aeiouAEIOU])", r"\1n \2", body)

    # Restore citations.
    body = re.sub(r"\x00CITE(\d+)\x00", lambda m: masked[int(m.group(1))], body)
    return body, fired


def styleguide_block() -> str:
    """Render the canonical-term table for the writer system prompt."""
    lines = ["TERMINOLOGY (canonical forms — use these, not variants):"]
    for canonical, variants in CANONICAL_TERMS.items():
        if not variants:
            continue
        lines.append(f"  - {canonical}  (NOT: {', '.join(variants)})")
    return "\n".join(lines)


# --- Sitrep-level pass ---------------------------------------------------------

# Field names on SitrepOut whose contents are free-text and should be passed
# through normalize_text. Lists/strings only — structured fields (tags,
# sources) are not free-text and are not rewritten.
_TEXT_FIELDS = ("bluf", "topline", "analysis")
_LIST_FIELDS = ("highlights", "osintIndicators", "predictions",
                "predictionsStable", "predictionsEscalatory")


def apply_style_to_sitrep(sitrep, log=None) -> int:
    """Rewrite every free-text surface on a SitrepOut to canonical terms.

    Returns the number of variant occurrences rewritten (for logging).
    """
    fired_total = 0
    fired_terms: list[str] = []

    def _fix_str(s: str | None) -> str | None:
        nonlocal fired_total, fired_terms
        if not s:
            return s
        new, fired = normalize_text(s)
        if fired:
            fired_total += len(fired)
            fired_terms.extend(fired)
        return new

    for f in _TEXT_FIELDS:
        cur = getattr(sitrep, f, None)
        if isinstance(cur, str):
            setattr(sitrep, f, _fix_str(cur))

    for f in _LIST_FIELDS:
        cur = getattr(sitrep, f, None)
        if isinstance(cur, list):
            setattr(sitrep, f, [_fix_str(x) if isinstance(x, str) else x for x in cur])

    # Sections: title + body.
    for sec in getattr(sitrep, "sections", []) or []:
        if hasattr(sec, "title") and isinstance(sec.title, str):
            sec.title = _fix_str(sec.title)
        if hasattr(sec, "body") and isinstance(sec.body, str):
            sec.body = _fix_str(sec.body)

    # Analysis points: each has a body field.
    for ap in getattr(sitrep, "analysisPoints", []) or []:
        if hasattr(ap, "body") and isinstance(ap.body, str):
            ap.body = _fix_str(ap.body)
        if hasattr(ap, "title") and isinstance(ap.title, str):
            ap.title = _fix_str(ap.title)

    # Timeline labels.
    for ev in getattr(sitrep, "timeline", []) or []:
        if hasattr(ev, "label") and isinstance(ev.label, str):
            ev.label = _fix_str(ev.label)

    if fired_total and log is not None:
        # Dedup for log noise but report total occurrences.
        unique = sorted(set(fired_terms))
        log.info(
            "style: rewrote %d variant occurrence(s) → canonical (%s)",
            fired_total, ", ".join(unique),
        )
    return fired_total


__all__ = [
    "CANONICAL_TERMS",
    "normalize_text",
    "styleguide_block",
    "apply_style_to_sitrep",
]
