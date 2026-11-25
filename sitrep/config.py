"""All settings come from the environment (see .env.example). Nothing personal lives in code."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def flag(key: str, default: bool = False) -> bool:
    return env(key, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def items(key: str) -> list[str]:
    return [x.strip() for x in env(key).split(",") if x.strip()]


def data_dir() -> Path:
    p = Path(env("DATA_DIR", str(ROOT / "data")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def prompt(name: str) -> str:
    from .schemas import SECTION_KEYS
    base = Path(env("PROMPTS_DIR", str(ROOT / "prompts")))
    t = (base / f"{name}.md").read_text()
    if "{{HOUSE_RULES}}" in t:
        t = t.replace("{{HOUSE_RULES}}", (base / "house-rules.md").read_text())
    return t.replace("{{SECTION_KEYS}}", ", ".join(f"`{k}`" for k in SECTION_KEYS))
