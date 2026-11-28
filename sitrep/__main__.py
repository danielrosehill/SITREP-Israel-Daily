"""python -m sitrep run [--no-deliver] | render <run dir> | deliver <run dir> [--only email] | site-build <dir> | serve"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import audio, deliver, llm, pipeline, render, site
from .config import data_dir, env, items
from .schemas import SitrepOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("sitrep")


def tz() -> ZoneInfo:
    return ZoneInfo(env("TZ", "Asia/Jerusalem"))


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def print_today(now: datetime | None = None) -> bool:
    """PRINT_DAYS: comma list of weekdays (sun,mon,...; full names work too). Empty or 'all' = every day.
    Checked against the local date (TZ) at delivery time."""
    days = [d.lower()[:3] for d in items("PRINT_DAYS")]
    if not days or "all" in days:
        return True
    bad = [d for d in days if d not in DAYS]
    if bad:
        log.warning("PRINT_DAYS: ignoring unknown day(s) %s", ", ".join(bad))
    return DAYS[(now or datetime.now(tz())).weekday()] in days


def deliver_run(run: Path, only: list[str] | None = None) -> bool:
    s = SitrepOut.model_validate_json((run / "sitrep.json").read_text())
    il = s.issuedAtUtc.astimezone(tz())
    pdf = next(run.glob("*.pdf"))
    files = [pdf, *run.glob("*.mp3")]
    md = s.newsletterMarkdown or f"# Subject: {s.title}\n\n{s.bluf}"
    channels = {
        "drive": (bool(env("RCLONE_DEST")), lambda: deliver.drive(files, f"{il:%Y}/{il:%m}")),
        "print": (env("PRINT_ENABLED") == "true" and print_today(), lambda: deliver.printer(pdf)),
        "email": (bool(items("EMAIL_TO") or items("EMAIL_GROUPS")),
                  lambda: deliver.email(md, s.title, f"{il:%A %-d %B %Y}", files)),
        "buttondown": (env("BUTTONDOWN_MODE", "off") in ("draft", "send"), lambda: deliver.buttondown(md, s.title)),
        # PDF only: a daily MP3 would grow the site repo by about 1 GB a year
        "site": (bool(env("SITE_REPO")), lambda: site.publish(s, md, il, [pdf])),
    }
    path = run / "status.json"
    status = json.loads(path.read_text()) if path.exists() else {}
    ok = True
    for name, (enabled, fn) in channels.items():
        if only and name not in only or not only and not enabled:
            continue
        try:
            status[name] = {"ok": True, "detail": fn()}
        except Exception as ex:
            detail = f"{ex} {getattr(ex, 'stderr', '') or ''}".strip()
            status[name], ok = {"ok": False, "detail": detail}, False
            log.error("%s failed: %s", name, detail)
        path.write_text(json.dumps(status, indent=1))
    log.info("delivery: %s", json.dumps(status))
    if not ok:
        raise RuntimeError("delivery problem in " + run.name + "\n" + json.dumps(status, indent=1))
    return ok


def run_once(args) -> Path:
    llm.COST["usd"] = 0.0
    s, evidence, script = pipeline.run(args.hours, args.focus, args.url)
    il = s.issuedAtUtc.astimezone(tz())
    run = data_dir() / "runs" / f"{il:%Y-%m-%dT%H%M}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "sitrep.json").write_text(s.model_dump_json(indent=1))
    (run / "evidence.json").write_text(json.dumps([e.model_dump(mode="json") for e in evidence], indent=1))
    base = f"SITREP-Israel-{il:%Y-%m-%d}"
    render.pdf(s, run / f"{base}.pdf")
    audio_error = None
    if script:
        (run / "briefing.txt").write_text(script)
        try:
            audio.synth(script, run / f"{base}.mp3")
        except Exception as ex:  # no audio is better than no report
            audio_error = str(ex)
            log.error("audio failed: %s", ex)
    (run / "status.json").write_text(json.dumps({
        "llm_cost_usd": round(llm.COST["usd"], 4), "tts_chars": len(script), "evidence": len(evidence),
        "audio": {"ok": not audio_error, "detail": audio_error}}, indent=1))
    log.info("run written: %s (LLM $%.4f, TTS %d chars)", run, llm.COST["usd"], len(script))
    if args.deliver:
        deliver_run(run)
    return run


def guarded(args) -> bool:
    try:
        run_once(args)
        return True
    except Exception as ex:
        log.exception("run failed")
        try:
            deliver.alert(str(ex))
        except Exception:
            log.exception("could not send the failure alert")
        return False


def serve(args) -> None:
    from croniter import croniter
    expr = env("SCHEDULE_CRON", "0 8 * * *")
    while True:
        nxt = croniter(expr, datetime.now(tz())).get_next(datetime)
        log.info("next run %s", nxt.isoformat())
        while (left := nxt.timestamp() - time.time()) > 0:
            time.sleep(min(left, 60))
        guarded(args)


def main() -> None:
    p = argparse.ArgumentParser(prog="sitrep")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "serve"):
        x = sub.add_parser(name)
        x.add_argument("--hours", type=float, default=float(env("COVERAGE_HOURS", "24")))
        x.add_argument("--focus", default="")
        x.add_argument("--url", action="append", default=[])
        x.add_argument("--no-deliver", dest="deliver", action="store_false")
    for name in ("render", "deliver"):
        x = sub.add_parser(name)
        x.add_argument("run_dir", type=Path)
        x.add_argument("--only", action="append", choices=["drive", "print", "email", "buttondown", "site"])
    sub.add_parser("site-build").add_argument("site_dir", type=Path)
    a = p.parse_args()
    if a.cmd == "site-build":
        print(site.build(a.site_dir), "reports")
    elif a.cmd == "serve":
        serve(a)
    elif a.cmd == "run":
        sys.exit(0 if guarded(a) else 1)
    elif a.cmd == "deliver":
        deliver_run(a.run_dir, a.only)
    else:
        s = SitrepOut.model_validate_json((a.run_dir / "sitrep.json").read_text())
        pdfs = list(a.run_dir.glob("*.pdf"))
        print(render.pdf(s, pdfs[0] if pdfs else a.run_dir / "sitrep.pdf"))


if __name__ == "__main__":
    main()
