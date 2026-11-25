"""Delivery channels. Each is off unless configured, and one failing never blocks the others."""
from __future__ import annotations

import base64
import re
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path

import httpx
import markdown

from .config import env, items

FOOTER = "Compiled automatically from open sources by a language model. It can be wrong; check primary sources before acting."


def parse_newsletter(md: str, fallback: str) -> tuple[str, str, str]:
    subj = re.search(r"^\s*#\s*Subject:\s*(.+)$", md, re.M | re.I)
    pre = re.search(r"^\s*>\s*Preheader:\s*(.+)$", md, re.M | re.I)
    body = re.sub(r"^\s*(#\s*Subject:|>\s*Preheader:).*$", "", md, flags=re.M | re.I).strip()
    return (subj[1].strip() if subj else fallback), (pre[1].strip() if pre else ""), body


def _html(body: str, pre: str, eyebrow: str) -> str:
    # markdown passes raw HTML through, so neutralise tags coming from the model or a feed
    inner = markdown.markdown(body.replace("<", "&lt;"))
    return (f'<div style="display:none">{pre.replace("<", "&lt;")}</div><div style="max-width:640px;margin:auto;'
            'font:16px/1.55 Helvetica,Arial,sans-serif;color:#12181f">'
            f'<p style="border-bottom:3px solid #12355b;padding-bottom:6px;letter-spacing:.06em"><b>{env("REPORT_NAME", "SITREP ISRAEL")}</b>'
            f' &nbsp;<span style="color:#5d6873">{eyebrow}</span></p>{inner}'
            f'<p style="font-size:12px;color:#5d6873;border-top:1px solid #c4cbd2;padding-top:8px">{FOOTER}</p></div>')


def _send(to: str, subject: str, html: str, text: str, files: list[Path]) -> None:
    sender = env("EMAIL_FROM")
    if env("EMAIL_PROVIDER", "resend") == "smtp":
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = sender, to, subject
        m.set_content(text)
        m.add_alternative(html, subtype="html")
        for f in files:
            m.add_attachment(f.read_bytes(), filename=f.name, **(
                {"maintype": "audio", "subtype": "mpeg"} if f.suffix == ".mp3" else {"maintype": "application", "subtype": "pdf"}))
        with smtplib.SMTP(env("SMTP_HOST"), int(env("SMTP_PORT", "587")), timeout=60) as s:
            s.starttls()
            if env("SMTP_USER"):
                s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
            s.send_message(m)
        return
    r = httpx.post("https://api.resend.com/emails", timeout=120,
                   headers={"Authorization": f"Bearer {env('RESEND_API_KEY')}"},
                   json={"from": sender, "to": [to], "subject": subject, "html": html, "text": text,
                         "attachments": [{"filename": f.name, "content": base64.b64encode(f.read_bytes()).decode()} for f in files]})
    if r.status_code >= 400:
        raise RuntimeError(f"Resend {r.status_code}: {r.text[:300]}")


def email(md: str, title: str, eyebrow: str, files: list[Path]) -> str:
    """EMAIL_TO = people, EMAIL_GROUPS = mailing-list addresses. One message each, so nobody sees the others."""
    subject, pre, body = parse_newsletter(md, title)
    to = list(dict.fromkeys(items("EMAIL_TO") + items("EMAIL_GROUPS")))
    errors = []
    for addr in to:
        try:
            _send(addr, f"[SITREP] {subject}", _html(body, pre, eyebrow), f"{body}\n\n{FOOTER}", files)
        except Exception as ex:
            errors.append(f"{addr}: {ex}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return f"sent to {len(to)} address(es)"


def alert(message: str) -> None:
    for addr in items("EMAIL_TO")[:1]:
        _send(addr, "[SITREP] run failed", f"<pre>{message.replace('<', '&lt;')}</pre>", message, [])


def drive(files: list[Path], folder: str) -> str:
    """Any rclone remote: RCLONE_DEST=gdrive:Path/To/Folder"""
    dest = f"{env('RCLONE_DEST').rstrip('/')}/{folder}"
    for f in files:
        subprocess.run(["rclone", "copy", str(f), dest], check=True, timeout=300, capture_output=True, text=True)
    return dest


def printer(pdf: Path) -> str:
    """PRINT_DRIVER=hub: LAN-Print-Hub HTTP API. PRINT_DRIVER=cups: lp to a CUPS server."""
    copies = env("PRINT_COPIES", "1")
    if env("PRINT_DRIVER", "hub") == "cups":
        cmd = ["lp", "-n", copies]
        if env("CUPS_SERVER"):
            cmd += ["-h", env("CUPS_SERVER")]
        if env("CUPS_QUEUE"):
            cmd += ["-d", env("CUPS_QUEUE")]
        if env("PRINT_SIDES"):
            cmd += ["-o", f"sides={env('PRINT_SIDES')}"]
        return subprocess.run([*cmd, str(pdf)], check=True, timeout=60, capture_output=True, text=True).stdout.strip()
    data = {"copies": copies}
    if env("PRINT_TARGET"):
        data["target"] = env("PRINT_TARGET")
    if env("PRINT_SIDES"):
        data["sides"] = env("PRINT_SIDES")
    r = httpx.post(f"{env('PRINT_HUB_URL').rstrip('/')}/jobs", params={"wait": "true"}, data=data, timeout=300,
                   files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
    r.raise_for_status()
    j = r.json()
    if j.get("state") == "error" or j.get("error"):
        raise RuntimeError(f"print job {j.get('id')}: {j.get('error')}")
    return f"job {j.get('id')} {j.get('state')}"


def buttondown(md: str, title: str) -> str:
    """BUTTONDOWN_MODE=draft stages the issue; send mails every subscriber."""
    subject, pre, body = parse_newsletter(md, title)
    send = env("BUTTONDOWN_MODE") == "send"
    headers = {"Authorization": f"Token {env('BUTTONDOWN_API_KEY')}"}
    if send:
        headers["X-Buttondown-Live-Dangerously"] = "true"
    r = httpx.post("https://api.buttondown.com/v1/emails", timeout=60, headers=headers,
                   json={"subject": subject, "description": pre, "body": f"{body}\n\n---\n\n_{FOOTER}_",
                         "status": "about_to_send" if send else "draft"})
    if r.status_code >= 400:
        raise RuntimeError(f"Buttondown {r.status_code}: {r.text[:300]}")
    return f"{r.json().get('status')} {r.json().get('id')}"
