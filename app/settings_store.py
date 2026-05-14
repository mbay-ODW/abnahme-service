"""Settings store: file-based persistence for runtime configuration.

Layout under DATA_DIR:
    settings.json        - runtime settings (API key, model, surcharges, ...)
    skill.md             - effective skill prompt (editable)
    skill.original.md    - immutable copy for reset/diff
    template.pdf         - active PDF template
    positions.json       - field coordinates for active template
    customers.json       - customer name + rate memory (existing)

First-run bootstrap: anything missing gets copied from the image defaults.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
APP_DIR = Path(__file__).parent
DEFAULT_TEMPLATE_DIR = APP_DIR / "default_template"
DEFAULT_SKILL = APP_DIR / "skill_prompt.md"

SETTINGS_PATH = DATA_DIR / "settings.json"
SKILL_PATH = DATA_DIR / "skill.md"
SKILL_ORIG_PATH = DATA_DIR / "skill.original.md"
TEMPLATE_PATH = DATA_DIR / "template.pdf"
POSITIONS_PATH = DATA_DIR / "positions.json"
PDFS_DIR = DATA_DIR / "pdfs"

# Defaults that get written on first run
DEFAULT_SETTINGS: dict[str, Any] = {
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-6",
    "surcharge_night_pct": 30,
    "surcharge_sunday_pct": 50,
    "surcharge_holiday_pct": 100,
}


def ensure_bootstrap() -> None:
    """Make sure all editable assets exist in DATA_DIR. Copy defaults on first
    run. Idempotent — safe to call on every startup."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDFS_DIR.mkdir(parents=True, exist_ok=True)

    if not SETTINGS_PATH.exists():
        _write_json(SETTINGS_PATH, DEFAULT_SETTINGS)
        log.info("Bootstrapped %s", SETTINGS_PATH)

    if not SKILL_ORIG_PATH.exists() and DEFAULT_SKILL.exists():
        shutil.copy2(DEFAULT_SKILL, SKILL_ORIG_PATH)
        log.info("Bootstrapped %s", SKILL_ORIG_PATH)

    if not SKILL_PATH.exists() and SKILL_ORIG_PATH.exists():
        shutil.copy2(SKILL_ORIG_PATH, SKILL_PATH)
        log.info("Bootstrapped %s", SKILL_PATH)

    if not TEMPLATE_PATH.exists():
        src = DEFAULT_TEMPLATE_DIR / "template.pdf"
        if src.exists():
            shutil.copy2(src, TEMPLATE_PATH)
            log.info("Bootstrapped %s", TEMPLATE_PATH)

    if not POSITIONS_PATH.exists():
        src = DEFAULT_TEMPLATE_DIR / "positions.json"
        if src.exists():
            shutil.copy2(src, POSITIONS_PATH)
            log.info("Bootstrapped %s", POSITIONS_PATH)


# ---------- Settings -------------------------------------------------------


def load_settings() -> dict[str, Any]:
    """Load settings.json, falling back to defaults for missing keys."""
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.exception("settings.json corrupt, returning defaults")
        return dict(DEFAULT_SETTINGS)
    # Merge over defaults so new keys appear after upgrade
    merged = dict(DEFAULT_SETTINGS)
    merged.update(loaded)
    return merged


def save_settings(partial: dict[str, Any]) -> dict[str, Any]:
    """Patch settings.json with provided keys. Returns the full new state."""
    current = load_settings()
    current.update(partial)
    _write_json(SETTINGS_PATH, current)
    return current


def get_setting(key: str, default: Any = None) -> Any:
    return load_settings().get(key, default)


def get_api_key() -> str:
    """Resolution order: env var (for CI/legacy) > settings.json."""
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    return load_settings().get("anthropic_api_key", "") or ""


def get_model() -> str:
    env = os.environ.get("ANTHROPIC_MODEL", "").strip()
    if env:
        return env
    return load_settings().get(
        "anthropic_model", DEFAULT_SETTINGS["anthropic_model"]
    )


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return "•" * len(key)
    return key[:7] + "…" + key[-4:]


# ---------- Skill ---------------------------------------------------------


def load_skill() -> str:
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    if DEFAULT_SKILL.exists():
        return DEFAULT_SKILL.read_text(encoding="utf-8")
    return ""


def load_skill_original() -> str:
    if SKILL_ORIG_PATH.exists():
        return SKILL_ORIG_PATH.read_text(encoding="utf-8")
    if DEFAULT_SKILL.exists():
        return DEFAULT_SKILL.read_text(encoding="utf-8")
    return ""


def save_skill(content: str) -> None:
    SKILL_PATH.write_text(content, encoding="utf-8")


def reset_skill() -> None:
    """Restore skill.md from skill.original.md."""
    orig = load_skill_original()
    if orig:
        SKILL_PATH.write_text(orig, encoding="utf-8")


# ---------- Template ------------------------------------------------------


def load_positions() -> dict[str, Any]:
    if POSITIONS_PATH.exists():
        try:
            return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.exception("positions.json corrupt")
    # Fallback to bundled default
    src = DEFAULT_TEMPLATE_DIR / "positions.json"
    if src.exists():
        return json.loads(src.read_text(encoding="utf-8"))
    return {}


def save_positions(positions: dict[str, Any]) -> None:
    _write_json(POSITIONS_PATH, positions)


def template_path() -> Path:
    """Path to the active template PDF."""
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH
    return DEFAULT_TEMPLATE_DIR / "template.pdf"


def save_template_pdf(content: bytes) -> None:
    TEMPLATE_PATH.write_bytes(content)


def reset_template() -> None:
    """Restore the bundled default template + positions."""
    src_pdf = DEFAULT_TEMPLATE_DIR / "template.pdf"
    src_pos = DEFAULT_TEMPLATE_DIR / "positions.json"
    if src_pdf.exists():
        shutil.copy2(src_pdf, TEMPLATE_PATH)
    if src_pos.exists():
        shutil.copy2(src_pos, POSITIONS_PATH)


# ---------- Helpers -------------------------------------------------------


def _write_json(path: Path, obj: Any) -> None:
    """Atomic write: tmp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
