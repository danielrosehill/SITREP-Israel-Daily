# SITREP Israel house style

One look and one voice for every channel: PDF (`templates/sitrep.typ`), email (`sitrep/deliver.py`), newsletter, website and the Android index app. Change a token here first, then in each channel.

Decided 2026-11-28: the printed PDF is the reference; the email was brought into line with it the same day. The old website (sitrepisr.com, repo `SITREP_ISR`, last post 2026-10-07) is replaced by the static site the `site` channel generates (`sitrep/site.py`), which uses these tokens.

## Colours

| Token | Hex | Use |
|---|---|---|
| ink | `#1a1f26` | body text |
| mute | `#66717d` | dates, eyebrows, footers |
| hair | `#cfd5db` | rules, dividers |
| wash | `#f2f5f8` | panels, card backgrounds |
| navy | `#12355b` | masthead, section headings |
| teal | `#0b7a75` | region/front labels, numbers |

## Type

- Body: IBM Plex Sans (email falls back to Helvetica, Arial).
- Masthead, section headings, numbers: IBM Plex Mono, bold, uppercase, tracked about 0.06-0.08em.
- Region/front labels (`### Iran`): sans bold, teal.
- Masthead reads `SITREP ISRAEL` plus a muted date, over a 3px navy rule.

## Prose

- Short paragraphs: 1-2 sentences, never more than 3 sentences or about 60 words. One development per paragraph. Readers are on phones. (Owner feedback on the first email, 2026-11-28.)
- Neutral analytical voice, no "we", no marketing tone (`prompts/house-rules.md`).
- No pipeline references ("since the last report").
