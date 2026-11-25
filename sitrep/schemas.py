from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Urgency = Literal["flash", "priority", "routine", "background"]
QuadClass = Literal[1, 2, 3, 4]
Cadence = Literal["daily", "weekly"]
Edition = Literal["morning", "evening"]
UrgencyScore = Literal[0, 1, 2, 3, 4, 5]


class TriageResult(BaseModel):
    urgency: Urgency
    flagged: bool = Field(
        description="True if the period warrants a full SITREP; false for heartbeat.",
    )
    has_new_material: bool = Field(
        default=True,
        description=(
            "True if, compared to the prior SITREP, there are genuinely new events, "
            "claims, or escalations worth surfacing. False if the picture is the same "
            "as the prior SITREP (duplication guard). Ignored when there is no prior."
        ),
    )
    hot_topics: list[str] = Field(default_factory=list)
    justification: str


class Evidence(BaseModel):
    source_name: str
    source_tier: str  # primary | primary-adversarial | wire | osint | analysis | dissident | telegram | manual
    url: str
    fetched_at: datetime
    title: str
    body_excerpt: str
    published_at: Optional[datetime] = None
    source_reliability: str = "mainstream"  # trusted | mainstream | caution | propaganda
    source_alignment: str = "independent"   # israel | us | multilateral | iran-dissident | axis | independent | arab-state
    dup_count: int = Field(
        default=1,
        description=(
            "Number of feeds that carried the same story (post-title-dedup). "
            "Writer uses this for proportionality: saturated stories (dup_count>=4) "
            "get a tight paragraph; thin-sourced credible signals (dup_count==1) "
            "deserve MORE real estate."
        ),
    )


class SitrepSection(BaseModel):
    key: str
    title: str
    body: str


# Allowed section keys. Backend always emits the full shape (with NOSIG body
# when nothing landed); the reader decides what renders. Order matches the
# reader's section ordering: classical fronts first, then antisemitism, then
# Israel-in-the-World continent buckets.
SECTION_KEYS = (
    "iran",
    "lebanon_hezbollah",
    "gaza",
    "west_bank",
    "multilateral",
    "antisemitism",
    "world_africa",
    "world_europe",
    "world_americas",
    "world_asia_pacific",
    "world_mena_other",
)


class TimelineEvent(BaseModel):
    """Single event on the SITREP timeline strip.

    Reader gates timeline rendering on `coverage_hours >= 12`. Numbering /
    chronology is reader-side; backend just emits events in chronological order.
    """
    utc: datetime = Field(description="Event time in UTC.")
    label: str = Field(description="One-line event description (≤ 120 chars).")
    front: str = Field(
        description="Front / section key the event belongs to (one of SECTION_KEYS).",
    )
    cameo_code: Optional[str] = Field(
        default=None,
        description="CAMEO event code — reserved/additive. Not populated yet; "
                    "kept here so wiring it in later is a pure additive change.",
    )


class SitrepSourceRef(BaseModel):
    name: str
    url: str


class SourceLink(BaseModel):
    slug: str
    name: Optional[str] = None
    citedUrl: Optional[str] = None
    note: Optional[str] = None


class LocationLink(BaseModel):
    slug: str
    section: Optional[str] = None
    note: Optional[str] = None


class ModelContributor(BaseModel):
    name: Optional[str] = None
    model: str
    role: Optional[str] = None
    lineage: Optional[str] = None


class ModelAttribution(BaseModel):
    writer: Optional[str] = None
    contributors: list[ModelContributor] = Field(default_factory=list)
    promptVersion: Optional[str] = None
    codeCommit: Optional[str] = None


ChangeDirection = Literal["added", "escalated", "de-escalated", "unchanged-but-reframed"]
# Numeric confidence in [0, 1] with 0.01 granularity (validated downstream).
# Back-compat: older SITREPs may carry enum strings "high"/"medium"/"low" —
# parsers in the web app coerce those to numeric (high≈0.80, medium≈0.50,
# low≈0.25). New writes should always emit floats.
PredictionConfidence = float


class KeyAssumption(BaseModel):
    text: str = Field(description="Assumption riding under the BLUF / topline.")
    falsifier: str = Field(description="What, if observed, would invalidate it.")


class ChangeSincePrior(BaseModel):
    text: str
    direction: ChangeDirection


PredictionLens = Literal["stable", "escalatory"]


class PredictionStructured(BaseModel):
    text: str = Field(description="Falsifiable claim, no confidence suffix.")
    horizonEndUtc: datetime = Field(description="Resolution deadline (UTC).")
    resolutionSource: str = Field(
        description="Where we will look to resolve this (e.g. 'IDF Spokesperson', 'Reuters wire', 'IAEA report').",
    )
    confidence: PredictionConfidence = Field(
        ge=0.0, le=1.0,
        description="Model confidence in [0, 1], 0.01 granularity.",
    )
    lens: Optional[PredictionLens] = Field(
        default=None,
        description="Which forecasting lens this prediction sits under: 'stable' (status-quo) "
                    "or 'escalatory' (max-escalation). Optional for back-compat with old SITREPs.",
    )


class AnalysisPoint(BaseModel):
    heading: str = Field(description="Short label for the point (e.g. 'Trend', 'Narrative', 'Synthesis').")
    body: str = Field(description="One short paragraph (3-6 sentences) developing the point.")


HomefrontTier = Literal["routine", "limited", "full"]


class HomefrontPosture(BaseModel):
    tier: HomefrontTier = Field(
        description="Pikud HaOref-equivalent posture: routine | limited | full.",
    )
    note: str = Field(
        description="One short sentence describing the current homefront posture and what changed.",
    )


class SitrepOut(BaseModel):
    title: str
    urlSlug: Optional[str] = Field(
        default=None,
        description="Kebab-case news slug derived from the lead event, e.g. 'us-seizes-mv-touska'.",
    )
    bluf: str
    highlights: list[str] = Field(default_factory=list, min_length=3, max_length=3)
    topline: str
    sections: list[SitrepSection]
    osintIndicators: list[str] = Field(default_factory=list, min_length=3, max_length=3)
    # Legacy single-string analysis + flat predictions list. Kept nullable so
    # back-edits of older SITREPs still validate; new SITREPs leave them empty
    # and populate `analysisPoints` + `predictionsStable` / `predictionsEscalatory`.
    predictions: list[str] = Field(default_factory=list)
    analysis: Optional[str] = None
    analysisPoints: Optional[list[AnalysisPoint]] = Field(
        default=None,
        description="EXACTLY 3 analysis points with semantic roles: "
                    "[0]=Trend (vs trailing N), [1]=Narrative (info-environment read), "
                    "[2]=Synthesis (the non-obvious interpretive claim).",
    )
    predictionsStable: Optional[list[str]] = Field(
        default=None,
        description="EXACTLY 3 status-quo-lens predictions, each ending in [confidence: 0.XX].",
    )
    predictionsEscalatory: Optional[list[str]] = Field(
        default=None,
        description="EXACTLY 3 max-escalation-lens predictions, each ending in [confidence: 0.XX].",
    )
    homefrontPosture: Optional[HomefrontPosture] = Field(
        default=None,
        description="Pikud HaOref-equivalent posture (routine | limited | full) + one-sentence note.",
    )
    emergencyLevel: bool = Field(
        default=False,
        description=(
            "True ONLY when the analyst is essentially certain that a major event "
            "is imminent — within the next few hours up to one day. This is the "
            "highest-confidence escalation flag and triggers an immediate Buttondown "
            "newsletter send, bypassing the normal 20:00 IL cadence. False for every "
            "routine, priority, or even flash-urgency SITREP that does not meet the "
            "imminent + near-certain bar. When in doubt, set to false."
        ),
    )
    sources: list[SitrepSourceRef]
    sourceRefs: list[SourceLink] = Field(default_factory=list)
    locationRefs: list[LocationLink] = Field(default_factory=list)
    tags: list[str]
    urgency: Urgency
    urgencyScore: Optional[UrgencyScore] = Field(
        default=None,
        description="0–5 numeric score from the scoring agent. Anchored: 0=quiet, "
                    "1=background, 2=routine, 3=notable, 4=significant, 5=critical. "
                    "Independent of the legacy `urgency` enum; both are surfaced.",
    )
    edition: Optional[Edition] = Field(
        default=None,
        description="Auto-derived from issuedAtUtc rendered in IL: morning if before 12:00, else evening.",
    )
    cadence: Cadence = "daily"
    quadClass: Optional[QuadClass] = None
    goldstein: Optional[int] = Field(default=None, ge=-10, le=10)
    magnitude: Optional[int] = Field(default=None, ge=1, le=5)
    issuedAtUtc: datetime
    coverageFromUtc: Optional[datetime] = None
    models: Optional[ModelAttribution] = None

    # --- Phase-1 tradecraft extensions (client-side; stripped at publish until
    # the admin ingest schema is extended to accept them). ---
    keyAssumptions: Optional[list[KeyAssumption]] = Field(
        default=None,
        description="2-4 load-bearing assumptions under the synthesis, each with a falsifier. "
                    "Surfaces the writer's priors so they can be challenged.",
    )
    changesSincePrior: Optional[list[ChangeSincePrior]] = Field(
        default=None,
        description="Required in short-delta mode: what changed vs. the prior SITREP and in which direction.",
    )
    predictionsStructured: Optional[list[PredictionStructured]] = Field(
        default=None,
        description="Machine-readable predictions with resolution deadline + source + lens. "
                    "6 entries total (3 stable + 3 escalatory) under the new schema; "
                    "parallel to legacy `predictions` (strings) for back-compat.",
    )
    sourceDiversity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="unique_outlets / total_citations across sourceRefs. Computed, not LLM-emitted.",
    )
    timeline: Optional[list[TimelineEvent]] = Field(
        default=None,
        description="Chronological events that occurred during the coverage window, "
                    "each anchored to a UTC instant. Reader renders as a numbered strip "
                    "only when `coverage_hours >= 12`. Null/empty when nothing landed.",
    )
    newsletterMarkdown: Optional[str] = Field(
        default=None,
        description="Buttondown-shaped newsletter body in markdown. First non-empty line is "
                    "the subject convention `# Subject: …`; second line is preheader "
                    "`> Preheader: …`; the rest is the email body. Produced by the newsletter "
                    "sub-agent; consumed by the Buttondown send path in the admin repo.",
    )
