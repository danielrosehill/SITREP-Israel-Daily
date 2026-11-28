"""Static website channel. No database, no server: plain files in a git repo that a static host
deploys on push. Each run adds reports/<date>/ (report.json + PDF); every page is then rebuilt
from the report.json files, so a style change only needs `python -m sitrep site-build <dir>`."""
from __future__ import annotations

import html
import json
import shutil
import subprocess
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

import markdown

from .config import ROOT, data_dir, env
from .deliver import FOOTER, HAIR, INK, MUTE, NAVY, TEAL, parse_newsletter

WASH = "#f2f5f8"
FONTS = ["IBMPlexSans-Regular", "IBMPlexSans-Bold", "IBMPlexSans-Italic", "IBMPlexMono-Bold", "IBMPlexMono-Medium"]

CSS = f"""@font-face{{font-family:"IBM Plex Sans";src:url(/assets/IBMPlexSans-Regular.ttf)}}
@font-face{{font-family:"IBM Plex Sans";font-weight:bold;src:url(/assets/IBMPlexSans-Bold.ttf)}}
@font-face{{font-family:"IBM Plex Sans";font-style:italic;src:url(/assets/IBMPlexSans-Italic.ttf)}}
@font-face{{font-family:"IBM Plex Mono";font-weight:bold;src:url(/assets/IBMPlexMono-Bold.ttf)}}
@font-face{{font-family:"IBM Plex Mono";font-weight:500;src:url(/assets/IBMPlexMono-Medium.ttf)}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:{INK};font:17px/1.6 "IBM Plex Sans",Helvetica,Arial,sans-serif}}
main{{max-width:640px;margin:auto;padding:20px 18px 48px}}
a{{color:{NAVY}}}
.mast{{display:block;font:bold 16px/1.3 "IBM Plex Mono",monospace;letter-spacing:.06em;color:{NAVY};text-decoration:none;
 border-bottom:3px solid {NAVY};padding-bottom:6px;margin-bottom:22px}}
.mast span,.date{{font-weight:500;color:{MUTE}}}
.date{{font:500 13px "IBM Plex Mono",monospace;letter-spacing:.04em}}
h1{{font-size:24px;line-height:1.3;margin:6px 0 6px}}
.pre{{color:{MUTE};margin:0 0 20px}}
h2{{font:bold 13px/1.3 "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:{NAVY};
 border-bottom:1px solid {HAIR};padding-bottom:4px;margin:30px 0 12px}}
h3{{font-size:16px;color:{TEAL};margin:20px 0 6px}}
p{{margin:0 0 14px}} ul{{padding-left:20px;margin:0 0 14px}} li{{margin:0 0 8px}}
.files a{{display:inline-block;font:bold 13px "IBM Plex Mono",monospace;letter-spacing:.06em;margin-right:16px}}
.latest{{display:block;background:{WASH};border-left:4px solid {NAVY};padding:14px 16px;margin:0 0 28px;color:{INK};text-decoration:none}}
.latest b{{display:block;font:bold 12px "IBM Plex Mono",monospace;letter-spacing:.08em;color:{TEAL};margin-bottom:4px}}
.latest strong{{display:block;font-size:20px;line-height:1.3;margin:4px 0}}
.list a{{display:block;padding:10px 0;border-bottom:1px solid {HAIR};color:{INK};text-decoration:none}}
.list a strong{{display:block;font-weight:bold;line-height:1.35}}
footer{{font-size:12px;color:{MUTE};border-top:1px solid {HAIR};padding-top:8px;margin-top:32px}}
"""


def _name() -> str:
    return env("REPORT_NAME", "SITREP Israel")


def _page(title: str, body: str, desc: str = "") -> str:
    e = html.escape
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<meta name="description" content="{e(desc)}"><link rel="stylesheet" href="/style.css">'
            f'<link rel="alternate" type="application/rss+xml" title="{e(_name())}" href="/rss.xml"></head><body><main>'
            f'<a class="mast" href="/">{e(_name().upper())}</a>{body}<footer>{e(FOOTER)}</footer></main></body></html>')


def _when(r: dict) -> str:
    return datetime.fromisoformat(r["issued"]).strftime("%A %-d %B %Y")


def reports(site: Path) -> list[dict]:
    out = [json.loads(p.read_text()) for p in (site / "reports").glob("*/report.json")]
    return sorted(out, key=lambda r: r["issued"], reverse=True)


def build(site: Path) -> int:
    """Rebuild every page, the RSS and JSON feeds, CSS and fonts from reports/*/report.json."""
    e = html.escape
    base = env("SITE_URL", "https://sitrepisr.com").rstrip("/")
    (site / "assets").mkdir(parents=True, exist_ok=True)
    for f in FONTS:
        shutil.copy(ROOT / "templates" / "fonts" / f"{f}.ttf", site / "assets" / f"{f}.ttf")
    (site / "style.css").write_text(CSS)
    rs = reports(site)
    for r in rs:
        files = "".join(f'<a href="{e(f)}">{e(f.rsplit(".", 1)[-1].upper())}</a>' for f in r.get("files", []))
        body = (f'<div class="date">{e(_when(r))}</div><h1>{e(r["subject"])}</h1><p class="pre">{e(r["preheader"])}</p>'
                + (f'<p class="files">{files}</p>' if files else "")
                # markdown passes raw HTML through, so neutralise tags coming from the model or a feed
                + markdown.markdown(r["body"].replace("<", "&lt;")))
        (site / "reports" / r["slug"] / "index.html").write_text(_page(f'{r["subject"]} | {_name()}', body, r["preheader"]))
    items = ""
    if rs:
        top = rs[0]
        items = (f'<a class="latest" href="/reports/{top["slug"]}/"><b>LATEST</b><span class="date">{e(_when(top))}</span>'
                 f'<strong>{e(top["subject"])}</strong>{e(top["preheader"])}</a><h2>All reports</h2><div class="list">'
                 + "".join(f'<a href="/reports/{r["slug"]}/"><span class="date">{e(_when(r))}</span>'
                           f'<strong>{e(r["subject"])}</strong></a>' for r in rs) + "</div>")
    (site / "index.html").write_text(_page(_name(), items or "<p>No reports yet.</p>", "Daily Israel situation report"))
    rss = "".join(
        f"<item><title>{e(r['subject'])}</title><link>{base}/reports/{r['slug']}/</link>"
        f"<guid>{base}/reports/{r['slug']}/</guid><pubDate>{format_datetime(datetime.fromisoformat(r['issued']))}</pubDate>"
        f"<description>{e(r['preheader'])}</description></item>" for r in rs[:60])
    (site / "rss.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(_name())}</title>'
        f"<link>{base}</link><description>Daily Israel situation report</description>{rss}</channel></rss>")
    (site / "feed.json").write_text(json.dumps({"name": _name(), "reports": [
        {k: r[k] for k in ("slug", "issued", "subject", "preheader")} | {"url": f"{base}/reports/{r['slug']}/"}
        for r in rs]}, indent=1))
    if env("SITE_DOMAIN"):
        (site / "CNAME").write_text(env("SITE_DOMAIN") + "\n")
    return len(rs)


def add(site: Path, sitrep, md: str, issued: datetime, files: list[Path]) -> str:
    slug = f"{issued:%Y-%m-%d}"
    subject, pre, body = parse_newsletter(md, sitrep.title)
    d = site / "reports" / slug
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(f, d / f.name)
    (d / "report.json").write_text(json.dumps({"slug": slug, "issued": issued.isoformat(), "subject": subject,
                                               "preheader": pre, "title": sitrep.title, "body": body,
                                               "files": [f.name for f in files]}, indent=1))
    return slug


def _git(site: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(site), *args], check=True, capture_output=True, text=True).stdout


def publish(sitrep, md: str, issued: datetime, files: list[Path]) -> str:
    """SITE_REPO=owner/name, SITE_TOKEN=a GitHub token that can push to it."""
    site = data_dir() / "site"
    url = f"https://x-access-token:{env('SITE_TOKEN')}@github.com/{env('SITE_REPO')}.git"
    if not (site / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--depth", "50", url, str(site)], check=True, capture_output=True, text=True)
    _git(site, "remote", "set-url", "origin", url)
    _git(site, "pull", "-q", "--rebase")
    slug = add(site, sitrep, md, issued, files)
    n = build(site)
    _git(site, "add", "-A")
    if not _git(site, "status", "--porcelain").strip():
        return f"{slug} unchanged"
    _git(site, "-c", "user.name=SITREP Israel", "-c", "user.email=sitrep@users.noreply.github.com",
         "commit", "-qm", f"Report {slug}")
    _git(site, "push", "-q")
    return f"{slug} published ({n} reports)"
