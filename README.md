# SITREP Israel Daily

Writes an Israel situation report from open sources every morning and delivers it as a typeset PDF, an audio briefing and an email. No website and no database: one small container and a folder of JSON files.

It is the successor to the SITREP ISR website and keeps that project's prompts, source whitelist, evidence tiers and editorial guards.

```
triage → research → informational (+ follow-up search) → analyst → guards → score → newsletter → audio script
                                  ↓
             Typst PDF + MP3 → email / groups / printer / cloud folder / Buttondown
```

Sample: [examples/SITREP-Israel-2026-11-25.pdf](examples/SITREP-Israel-2026-11-25.pdf)

## Run

```bash
cp .env.example .env         # every personal setting lives here
docker compose up -d         # waits for SCHEDULE_CRON (default 08:00 Asia/Jerusalem)
docker compose exec sitrep python -m sitrep run                # now, with delivery
docker compose exec sitrep python -m sitrep run --no-deliver   # write files only
docker compose exec sitrep python -m sitrep run --hours 12 --focus "northern front" --url https://...
docker compose exec sitrep python -m sitrep deliver data/runs/<run> --only print
docker compose exec sitrep python -m sitrep render data/runs/<run>
```

`deliver --only` ignores the enabled switches, so it can send one channel on demand.

## Delivery channels

Each is off until configured. If one fails the others still run, and the first `EMAIL_TO` address gets an alert.

| Channel | Settings |
|---|---|
| Email (Resend or SMTP) | `EMAIL_FROM`, `EMAIL_TO`, PDF and MP3 attached, one message per address |
| Group email | `EMAIL_GROUPS`: mailing-list addresses (the list must accept posts from `EMAIL_FROM`) |
| Printer | `PRINT_ENABLED=true`, then `PRINT_DRIVER=hub` ([LAN-Print-Hub](https://github.com/danielrosehill/LAN-Print-Hub)) or `cups` |
| Cloud folder | `RCLONE_DEST=remote:Folder`, config in `data/rclone.conf`; files go to `YYYY/MM/` |
| Buttondown | `BUTTONDOWN_MODE=off`, `draft` or `send` (text of the newsletter; `send` mails all subscribers) |

## Customise

- `prompts/*.md`: every system prompt. `PROMPTS_DIR` points at your own copies. `prompts/archive/` has the original single-pass writer prompt (unused).
- `grounding/grounding-set.md`: the source whitelist. `GROUNDING_SET_PATH` overrides it. Reliability ratings are in `sitrep/whitelist.py`.
- `templates/sitrep.typ`: the printed report. `TYPST_TEMPLATE` overrides it.
- `LLM_MODEL`, `TTS_MODEL`, `TTS_VOICE`: any OpenRouter model.

## Cost

Measured 2026-11-25 with the defaults: about $0.014 of LLM use, plus about 4,000-5,500 characters of speech at $4 per million characters (about $0.02). Roughly $1 a month. Exa follow-up searches are extra and optional.

## Limits

A language model writes the report from feed excerpts. URLs that were not in the evidence are removed, but the prose can still be wrong. Not a substitute for Home Front Command instructions.

MIT licence. IBM Plex fonts in `templates/fonts/` are under the SIL Open Font License.
