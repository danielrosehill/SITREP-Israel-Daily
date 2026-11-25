"""Parse grounding-set.md into structured source lists.

Sources are tiered by the markdown section they appear under.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


_DEFAULT_GROUNDING_SET = (
    Path(__file__).resolve().parents[1] / "grounding" / "grounding-set.md"
).resolve()

GROUNDING_SET_PATH = Path(
    os.environ.get("GROUNDING_SET_PATH", str(_DEFAULT_GROUNDING_SET))
)


@dataclass
class Source:
    name: str
    url: str
    tier: str
    is_rss: bool
    is_telegram: bool = False
    reliability: str = "mainstream"  # trusted | mainstream | caution | propaganda
    alignment: str = "independent"   # israel | us | multilateral | iran-dissident | axis | independent | arab-state


_SECTION_TIER = {
    "Primary state — Israel / US / allies": "primary",
    "Primary state — Iran / Axis of Resistance": "primary-adversarial",
    "Primary state — Lebanon / international bodies": "primary",
    "Wire & regional reporting": "wire",
    "OSINT synthesis": "osint",
    "Analysis — spanning the spectrum": "analysis",
    "Dissident & opposition": "dissident",
    "Telegram channels (public preview)": "telegram",
}

# Default reliability/alignment by section. Overridden per-domain below.
_SECTION_DEFAULT = {
    "primary":              ("trusted",    "us"),
    "primary-adversarial":  ("propaganda", "axis"),
    "wire":                 ("mainstream", "independent"),
    "osint":                ("trusted",    "independent"),
    "analysis":             ("mainstream", "independent"),
    "dissident":            ("caution",    "iran-dissident"),
    "telegram":             ("caution",    "independent"),
}

# Per-domain/channel overrides. Keys are bare hostnames (no www.) OR, for
# Telegram, the lowercase channel slug.
_DOMAIN_OVERRIDES: dict[str, tuple[str, str]] = {
    # --- Allied primary ---
    "idf.il":                ("trusted",    "israel"),
    "mfa.gov.il":            ("trusted",    "israel"),
    "state.gov":             ("trusted",    "us"),
    "centcom.mil":           ("trusted",    "us"),
    "nato.int":              ("trusted",    "us"),
    "lebarmy.gov.lb":        ("mainstream", "multilateral"),
    "unifil.unmissions.org": ("trusted",    "multilateral"),
    "iaea.org":              ("trusted",    "multilateral"),
    "news.un.org":           ("trusted",    "multilateral"),
    # --- Adversarial state media (explicit — these are regime/proxy mouthpieces) ---
    "irna.ir":               ("propaganda", "axis"),
    "en.irna.ir":            ("propaganda", "axis"),
    "tasnimnews.com":        ("propaganda", "axis"),
    "almasirah.net.ye":      ("propaganda", "axis"),
    "almanar.com.lb":        ("propaganda", "axis"),
    "mfa.gov.ir":            ("propaganda", "axis"),
    "en.mfa.gov.ir":         ("propaganda", "axis"),
    "almayadeen.net":        ("propaganda", "axis"),
    "english.almayadeen.net":("propaganda", "axis"),
    "presstv.ir":            ("propaganda", "axis"),
    # --- Wire ---
    "timesofisrael.com":     ("mainstream", "israel"),
    "jpost.com":             ("mainstream", "israel"),
    "bbci.co.uk":            ("mainstream", "independent"),
    "bbc.com":               ("mainstream", "independent"),
    "haaretz.com":            ("mainstream", "israel"),
    "aljazeera.com":         ("caution",    "arab-state"),
    "alarabiya.net":         ("mainstream", "arab-state"),
    "arabnews.com":          ("mainstream", "arab-state"),
    "israelnationalnews.com":("caution",    "israel"),
    # --- OSINT ---
    "bellingcat.com":        ("trusted",    "independent"),
    "acleddata.com":         ("trusted",    "independent"),
    "longwarjournal.org":    ("mainstream", "us"),
    "iransitrep.com":        ("mainstream", "independent"),
    "understandingwar.org":  ("mainstream", "us"),
    # --- Analysis ---
    "washingtoninstitute.org": ("mainstream", "us"),
    "inss.org.il":           ("mainstream", "israel"),
    "fdd.org":               ("mainstream", "us"),
    "crisisgroup.org":       ("mainstream", "multilateral"),
    "responsiblestatecraft.org": ("mainstream", "us"),
    # --- Dissident ---
    "iranintl.com":          ("caution",    "iran-dissident"),
    "iranwire.com":          ("caution",    "iran-dissident"),
    "syriahr.com":           ("mainstream", "independent"),
}

# Telegram channel overrides, keyed by lowercase channel slug (the path after t.me/).
_TELEGRAM_OVERRIDES: dict[str, tuple[str, str]] = {
    "idfofficial":          ("trusted",    "israel"),
    "manniefabian":         ("mainstream", "independent"),
    "news0404il":           ("mainstream", "israel"),
    "n12chat":              ("mainstream", "israel"),
    "bintjbeilnews":        ("caution",    "independent"),
    "israelhayomofficial":  ("mainstream", "israel"),
    "warmonitors":          ("caution",    "independent"),
    "qudsnen":              ("propaganda", "axis"),
    "beholdisraelchannel":  ("caution",    "israel"),
}


def _classify(url: str, tier: str) -> tuple[str, str]:
    """Return (reliability, alignment) for a source URL under a given section tier."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # Telegram: key off channel slug.
    if host == "t.me" or host.endswith(".t.me") or host == "telegram.me":
        slug = parsed.path.strip("/").split("/")[0].lower()
        if slug in _TELEGRAM_OVERRIDES:
            return _TELEGRAM_OVERRIDES[slug]
        return _SECTION_DEFAULT.get(tier, ("mainstream", "independent"))

    # Exact host match.
    if host in _DOMAIN_OVERRIDES:
        return _DOMAIN_OVERRIDES[host]
    # Suffix match (covers subdomains like english.almanar.com.lb).
    for dom, pair in _DOMAIN_OVERRIDES.items():
        if host.endswith("." + dom):
            return pair

    return _SECTION_DEFAULT.get(tier, ("mainstream", "independent"))


def classify_url(url: str, sources: list[Source] | None = None) -> tuple[str, str]:
    """Classify an arbitrary URL (e.g. an Exa result) using the same rules.

    Falls back to the 'wire' default when the host is unknown — Exa results
    are already whitelist-constrained, so the host should be known in practice.
    """
    sources = sources or parse_sources()
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for s in sources:
        shost = (urlparse(s.url).netloc or "").lower()
        if shost.startswith("www."):
            shost = shost[4:]
        if host == shost or host.endswith("." + shost) or shost.endswith("." + host):
            return s.reliability, s.alignment
    # Fallback
    if host in _DOMAIN_OVERRIDES:
        return _DOMAIN_OVERRIDES[host]
    return ("mainstream", "independent")


def _is_telegram(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "t.me" or host.endswith(".t.me") or host == "telegram.me"


def _looks_like_feed(url: str) -> bool:
    lower = url.lower()
    return (
        lower.endswith(".xml")
        or lower.endswith("/rss")
        or lower.endswith("/feed")
        or lower.endswith("/feed/")
        or "/rss/" in lower
        or "/feed/" in lower
        or "rss2" in lower
        or "?feed=" in lower
    )


def parse_sources(path: Path | None = None) -> list[Source]:
    md = (path or GROUNDING_SET_PATH).read_text()
    lines = md.splitlines()
    current_tier: str | None = None
    out: list[Source] = []

    name_url = re.compile(r"\*\*(?P<name>[^*]+)\*\*[^`<]*(?:`(?P<url1>[^`]+)`|<(?P<url2>https?://[^>]+)>)")

    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("# ").strip()
            current_tier = _SECTION_TIER.get(heading)
            continue
        if not current_tier:
            continue
        m = name_url.search(line)
        if not m:
            continue
        name = m.group("name").strip()
        url = (m.group("url1") or m.group("url2") or "").strip()
        if not url:
            continue
        try:
            urlparse(url)
        except Exception:
            continue
        reliability, alignment = _classify(url, current_tier)
        out.append(Source(
            name=name,
            url=url,
            tier=current_tier,
            is_rss=_looks_like_feed(url),
            is_telegram=_is_telegram(url),
            reliability=reliability,
            alignment=alignment,
        ))
    return out


def whitelist_domains(sources: list[Source] | None = None) -> set[str]:
    sources = sources or parse_sources()
    hosts: set[str] = set()
    for s in sources:
        host = urlparse(s.url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        hosts.add(host)
        if host.endswith("bbci.co.uk"):  # feed host differs from the article host
            hosts |= {"bbc.com", "bbc.co.uk"}
    return hosts


def assert_whitelisted(url: str, sources: list[Source] | None = None) -> None:
    hosts = whitelist_domains(sources)
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # allow subdomains of whitelisted hosts
    if host not in hosts and not any(host.endswith("." + h) for h in hosts):
        raise ValueError(f"URL not whitelisted: {url} (host={host})")


if __name__ == "__main__":
    srcs = parse_sources()
    for s in srcs:
        kind = "RSS" if s.is_rss else "   "
        print(f"[{s.tier:9}] {kind} {s.name} -- {s.url}")
    print(f"\n{len(srcs)} sources, {sum(1 for s in srcs if s.is_rss)} RSS")
