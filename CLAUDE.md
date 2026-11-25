# SITREP-Israel-Daily: agent notes

Public, generic repo. Never commit addresses, IPs, printer names or keys: they go in `.env`. Release tier: small (`v1.0`).

- Entry point `sitrep/__main__.py`; stages in `sitrep/pipeline.py`; channels in `sitrep/deliver.py`; PDF data in `sitrep/render.py` + `templates/sitrep.typ`.
- Archive is `data/runs/<local time>/` (`sitrep.json`, `evidence.json`, `status.json`, PDF, MP3). `recent_sitreps()` reads it for trend context.
- Model text reaches Typst as JSON, never as markup. Keep it that way.
- The image is built by `.github/workflows/image.yml` on push to main, to `ghcr.io/danielrosehill/sitrep-israel-daily`.

## Ported from SITREP_ISR (private), and what changed

- Live "deepagent" path kept; LangGraph, the admin API and the database dropped. Window is a fixed 24 h, always published (no heartbeat or short-delta gates).
- `prompts/analyst.md`: the old text asked for satellite orbits and passes, which the model invented and a guard stripped. Replaced with the ban from the archived writer prompt.
- Style, world-desk and fabricated-specifics guards now run on this path too (before, only on the legacy writer). Source URLs not in the evidence are dropped.
- `world_*` sections need an explicit Israel angle, so regional stories without one are pruned on purpose.

## Found 2026-11-25

- Feeds failing from Israel: Tasnim (DNS), Al Arabiya, Arab News, IAEA, Washington Institute (403), NATO, ACLED (404), Israel MFA (TLS). Non-fatal. Times of Israel main, JPost and BBC were added.
- OpenRouter `/audio/speech`: HeyGen voices return only `pcm`; the sample rate is in the response content type (44100 HeyGen, 24000 Gemini). `sitrep/audio.py` reads it.
- `sitrep/style.py` rewrites "settlers" to "Israeli citizens" (inherited editorial choice).
- `fonts-ibm-plex` is not installable in the `python:3.13-slim` image, so the fonts are vendored in `templates/fonts/`.
- Exa rejected every search with "Invalid URL": the ISW entry in the grounding set names a document, not a URL, so the domain list held an empty string. `whitelist_domains()` now skips it.
