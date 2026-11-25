"""Rule-based guards on the model output, ported from SITREP_ISR."""
from __future__ import annotations

import logging
import re

from .schemas import SitrepOut

log = logging.getLogger(__name__)

# Patterns that look like fabricated OSINT specifics — orbit numbers, satellite
# tasking IDs, NOTAM IDs, decimal-degree coordinates, Maxar/Sentinel pass
# timestamps. The writer cannot truthfully name these and historically
# hallucinates them. We strip the offending fragment rather than dropping the
# whole indicator, since the underlying advisory may still be useful.
_OSINT_FAB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # "orbit 42679" / "(orbit 108, ...)" — strip the bracketed/comma'd specifier
    (re.compile(r"\s*\(?\s*orbit\s+\d+[^)]*\)?", re.IGNORECASE), ""),
    # "next pass Apr 25 1830 UTC" or similar
    (re.compile(r",?\s*next pass [A-Z][a-z]{2}\s+\d{1,2}[^,)]*", re.IGNORECASE), ""),
    # Decimal-degree coordinate pairs: "33.898°N 35.514°E" or "(25.12°N, 56.33°E)"
    (re.compile(r"\s*\(?\s*\d{1,3}\.\d+°\s*[NS]\s*,?\s*\d{1,3}\.\d+°\s*[EW]\s*\)?"), ""),
    # "Sentinel-1 IW GRD orbit ..." — squash to "Sentinel-1 SAR coverage" if mid-sentence
    (re.compile(r"Sentinel-1\s+IW\s+GRD\s+orbit\s+\d+", re.IGNORECASE), "Sentinel-1 SAR coverage"),
    # "Maxar WorldView-3 tasked imagery of X" — drop "tasked" (claims tasking the writer can't know)
    (re.compile(r"Maxar\s+WorldView-\d+\s+tasked\s+imagery", re.IGNORECASE), "Maxar WorldView imagery"),
)


def _flag_osint_fabricated_specifics(sitrep: SitrepOut) -> None:
    """Strip fabricated specifics from osintIndicators and log when we do.

    Conservative: rewrites in place rather than dropping items. Items that
    become substantively empty after stripping are replaced with a generic
    placeholder so downstream length validation (>=3 items) still passes;
    in practice the writer rarely produces items shaped that way once the
    prompt is up to date.
    """
    if not sitrep.osintIndicators:
        return
    cleaned: list[str] = []
    fixed = 0
    for raw in sitrep.osintIndicators:
        cur = raw
        for pat, repl in _OSINT_FAB_PATTERNS:
            new = pat.sub(repl, cur)
            if new != cur:
                fixed += 1
                cur = new
        # Tidy up double-spaces / dangling punctuation left by deletions.
        cur = re.sub(r"\s{2,}", " ", cur).strip()
        cur = re.sub(r"\s+([,.;:])", r"\1", cur)
        cur = re.sub(r"\(\s*\)", "", cur).strip()
        if not cur:
            cur = raw  # fall back to original if we accidentally nuked it
        cleaned.append(cur)
    sitrep.osintIndicators = cleaned
    if fixed:
        log.warning(
            "osintIndicators: stripped %d fabricated-specific fragment(s)", fixed,
        )


_WORLD_KEYS = {
    "world_africa", "world_europe", "world_americas",
    "world_asia_pacific", "world_mena_other",
}
# Surface forms that count as an Israel angle in a world_* section body.
_ISRAEL_MENTION_RE = re.compile(
    r"\b(israel|israeli|jerusalem|idf|mossad|knesset|netanyahu|jewish|hebrew)\b",
    re.IGNORECASE,
)


def _flag_world_desk_off_topic(sitrep: SitrepOut) -> None:
    """Drop off-topic content from world_* sections.

    Hard rule from the styleguide: every item in a world_* (Israel-in-the-
    World) bucket must have an explicit Israel angle. The writer drifts in
    two ways:

    1. The whole section is off-topic (e.g. a Nepal-India border story
       sitting alone under world_asia_pacific). → replace body with NOSIG.
    2. The section has one valid Israel paragraph plus extra run-in heading
       blocks (e.g. **India** with West Bengal election violence, **China**
       with Taiwan strait news) that have no Israel angle. → drop just
       those blocks, keep the on-topic ones.

    This runs section-level then block-level: split the body at `**Heading**`
    run-in boundaries, keep only blocks that mention Israel/Israeli/IDF/etc.
    in their prose (citation brackets are masked first so [Times of Israel]
    doesn't smuggle a block through).
    """
    flagged_sections: list[str] = []
    pruned_blocks: list[tuple[str, str]] = []  # (section_key, heading)
    for section in sitrep.sections:
        if section.key not in _WORLD_KEYS:
            continue
        body = (section.body or "").strip()
        if not body or body.upper().startswith("NOSIG"):
            continue

        # Block-level prune. Split on lines that are exactly `**...**` —
        # those are run-in headings. Keep the heading attached to its block.
        lines = body.split("\n")
        blocks: list[list[str]] = []
        cur: list[str] = []
        heading_re = re.compile(r"^\*\*[^*]+\*\*\s*$")
        for ln in lines:
            if heading_re.match(ln.strip()):
                if cur:
                    blocks.append(cur)
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            blocks.append(cur)

        # If there are no run-in headings, fall through to whole-section
        # check (single block).
        if len(blocks) > 1:
            kept: list[list[str]] = []
            for blk in blocks:
                blk_text = "\n".join(blk)
                masked = re.sub(r"\[[^\]]+\]", "", blk_text)
                if _ISRAEL_MENTION_RE.search(masked):
                    kept.append(blk)
                else:
                    heading = blk[0].strip().strip("*").strip()
                    pruned_blocks.append((section.key, heading))
            if kept:
                section.body = "\n".join("\n".join(b) for b in kept).strip()
                continue
            # All blocks pruned — fall through to NOSIG below.
            body = ""

        masked = re.sub(r"\[[^\]]+\]", "", body)
        if not body or not _ISRAEL_MENTION_RE.search(masked):
            section.body = "NOSIG"
            section.title = ""
            flagged_sections.append(section.key)

    if flagged_sections:
        log.warning(
            "world-desk: rewrote %d off-topic section(s) to NOSIG (%s)",
            len(flagged_sections), ", ".join(flagged_sections),
        )
    if pruned_blocks:
        log.warning(
            "world-desk: pruned %d off-topic run-in block(s) (%s)",
            len(pruned_blocks),
            ", ".join(f"{k}/{h}" for k, h in pruned_blocks),
        )


def verify_sources(sitrep: SitrepOut, evidence) -> None:
    """Keep only source URLs that were really in the evidence; drop invented ones."""
    urls = {ev.url: ev.source_name for ev in evidence}
    kept, seen = [], set()
    for s in sitrep.sources:
        if s.url in urls and s.url not in seen:
            seen.add(s.url)
            kept.append(s)
    dropped = len(sitrep.sources) - len(kept)
    sitrep.sources = kept
    if dropped:
        log.warning("sources: dropped %d URL(s) not present in the evidence", dropped)


def apply(sitrep: SitrepOut, evidence) -> None:
    from .style import apply_style_to_sitrep
    _flag_osint_fabricated_specifics(sitrep)
    _flag_world_desk_off_topic(sitrep)
    apply_style_to_sitrep(sitrep, log=log)
    verify_sources(sitrep, evidence)
