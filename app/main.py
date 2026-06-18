"""FastAPI service for Abnahme-Protokolle.

Endpoints:
  GET  /api/customers                — known-customers cache
  POST /api/process                  — main pipeline (WhatsApp text -> PDF)
  GET  /api/pdf/{fname}              — serve a generated PDF (inline)

  GET  /api/settings                 — runtime settings (api_key masked)
  POST /api/settings                 — update settings
  POST /api/settings/test            — try a no-op Anthropic call

  GET  /api/skill                    — current skill + original (for diff)
  POST /api/skill                    — save skill
  POST /api/skill/reset              — reset to original

  GET  /api/template                 — current template metadata
  GET  /api/template/pdf             — serve current template PDF (inline)
  POST /api/template/upload          — multipart upload + Vision-analyze
  GET  /api/template/preview         — sample-data preview of current template
  POST /api/template/positions       — overwrite positions.json (JSON editor)
  POST /api/template/reset           — restore bundled default

  GET  /healthz                      — liveness probe
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from anthropic import Anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import settings_store
from .claude_client import process_message
from .pdf_stamper import stamp_pdf, stamp_preview, stamp_signature
from .settings_store import (
    DATA_DIR,
    PDFS_DIR,
    TEMPLATE_PATH,
    delete_logo,
    delete_signature,
    ensure_bootstrap,
    get_api_key,
    get_model,
    has_logo,
    has_signature,
    load_positions,
    load_settings,
    load_skill,
    load_skill_original,
    logo_path,
    mask_api_key,
    reset_skill,
    reset_template,
    save_logo,
    save_positions,
    save_settings,
    save_signature,
    save_skill,
    save_template_pdf,
    signature_path,
    template_path,
)
from .vision_client import analyze_template

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("abnahme")

ensure_bootstrap()

CUSTOMERS_PATH = DATA_DIR / "customers.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Abnahme-Service")


# ---------- Pydantic models ----------


class ProcessRequest(BaseModel):
    text: str
    kunde: str | None = None
    satz: float | None = None
    datum: str | None = None


class ProcessResponse(BaseModel):
    status: str
    fehlende_eingaben: list[str] = []
    pdf_url: str | None = None
    pdf_filename: str | None = None
    buchung: dict[str, Any] | None = None
    plausibilitaets_warnung: str | None = None
    erkannt: dict[str, Any] = {}
    known_customers: list[dict[str, Any]] = []


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    surcharge_night_pct: float | None = None
    surcharge_sunday_pct: float | None = None
    surcharge_holiday_pct: float | None = None


class SkillSave(BaseModel):
    content: str


class PositionsSave(BaseModel):
    positions: dict[str, Any]


# ---------- Customer memory ----------


def load_customers() -> dict[str, dict[str, Any]]:
    if not CUSTOMERS_PATH.exists():
        return {}
    try:
        return json.loads(CUSTOMERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.exception("customers.json corrupt, starting fresh")
        return {}


def save_customer(name: str, satz: float) -> None:
    if not name:
        return
    data = load_customers()
    data[name.strip().lower()] = {
        "name": name.strip(),
        "satz": satz,
        "last_used": datetime.utcnow().isoformat(),
    }
    CUSTOMERS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def known_customers_list() -> list[dict[str, Any]]:
    return sorted(
        load_customers().values(),
        key=lambda c: c.get("last_used", ""),
        reverse=True,
    )


# ---------- Filename helpers ----------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "kunde"


def filename_for(kunde: str, datum_iso: str | None) -> str:
    if not datum_iso:
        datum_iso = date.today().isoformat()
    return f"Abnahme-Protokoll_{slug(kunde)}_{datum_iso}.pdf"


def _extract_satz_from_bemerkung(bem: str) -> float | None:
    if not bem:
        return None
    m = re.search(r"(\d+[\.,]?\d*)\s*€", bem)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


# ---------- Main pipeline ----------


@app.get("/api/customers")
def get_customers() -> dict[str, Any]:
    return {"customers": known_customers_list()}


@app.post("/api/process", response_model=ProcessResponse)
def post_process(req: ProcessRequest) -> ProcessResponse:
    if not req.text or not req.text.strip():
        raise HTTPException(400, "text darf nicht leer sein")
    if not get_api_key():
        raise HTTPException(
            400,
            "API-Key fehlt. Bitte unter Einstellungen den Anthropic-API-Key "
            "hinterlegen.",
        )

    log.info(
        "Process: kunde=%r satz=%r datum=%r len(text)=%d",
        req.kunde, req.satz, req.datum, len(req.text),
    )

    try:
        result = process_message(
            text=req.text, kunde=req.kunde, satz=req.satz, datum=req.datum,
        )
    except Exception as exc:
        log.exception("Claude processing failed")
        raise HTTPException(500, f"Verarbeitung fehlgeschlagen: {exc}") from exc

    erkannt = {
        "kunde": result.get("kunde", ""),
        "satz": _extract_satz_from_bemerkung(result.get("bemerkung", ""))
        or req.satz,
        "datum": result.get("datum", ""),
    }

    if result["_status"] == "needs_input":
        return ProcessResponse(
            status="needs_input",
            fehlende_eingaben=result.get("fehlende_eingaben", []),
            erkannt=erkannt,
            known_customers=known_customers_list(),
        )

    # Build PDF using the stamper + active template + active positions
    pdf_data = {
        "kunde": result.get("kunde", ""),
        "objekt": result.get("objekt", ""),
        "projekt": result.get("projekt", ""),
        "best_nr": result.get("best_nr", ""),
        "datum": result.get("datum", ""),
        "rows": result.get("rows", []),
        "gesamt_summe": result.get("gesamt_summe", ""),
        "bemerkung": result.get("bemerkung", ""),
    }

    fname = filename_for(result.get("kunde", "kunde"), result.get("datum_iso"))
    out_path = PDFS_DIR / fname
    positions = load_positions()
    try:
        stamp_pdf(template_path(), positions, pdf_data, out_path)
    except Exception as exc:
        log.exception("PDF stamp failed")
        raise HTTPException(500, f"PDF-Bau fehlgeschlagen: {exc}") from exc

    # Stamp the signature image (bottom-left) if one has been uploaded.
    sig = signature_path()
    if sig:
        try:
            stamp_signature(out_path, sig, positions.get("signature"))
        except Exception:
            # A signature failure must not block protocol creation.
            log.exception("Signature stamp failed — continuing without it")

    if req.satz is not None and result.get("kunde"):
        save_customer(result["kunde"], req.satz)

    return ProcessResponse(
        status="complete",
        pdf_url=f"/api/pdf/{fname}",
        pdf_filename=fname,
        buchung=result.get("buchung"),
        plausibilitaets_warnung=result.get("plausibilitaets_warnung") or None,
        erkannt=erkannt,
    )


@app.get("/api/pdf/{fname}.png")
def get_pdf_png(fname: str) -> Response:
    """Rasterized first-page preview of a generated PDF.

    Note: this route must be declared BEFORE /api/pdf/{fname} — otherwise
    the latter's greedy path parameter swallows the `.png` suffix and the
    .pdf-validation in the other handler rejects the request.
    """
    import io
    from pdf2image import convert_from_path

    if "/" in fname or ".." in fname or not fname.endswith(".pdf"):
        raise HTTPException(400, "Ungültiger Dateiname")
    path = PDFS_DIR / fname
    if not path.exists():
        raise HTTPException(404, "PDF nicht gefunden")
    pages = convert_from_path(str(path), dpi=110, first_page=1, last_page=1)
    buf = io.BytesIO()
    pages[0].save(buf, format="PNG", optimize=True)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/pdf/{fname}")
def get_pdf(fname: str) -> FileResponse:
    if "/" in fname or ".." in fname or not fname.endswith(".pdf"):
        raise HTTPException(400, "Ungültiger Dateiname")
    path = PDFS_DIR / fname
    if not path.exists():
        raise HTTPException(404, "PDF nicht gefunden")
    return FileResponse(
        path, media_type="application/pdf", filename=fname,
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


# ---------- Settings ----------


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    s = load_settings()
    return {
        "anthropic_api_key_set": bool(s.get("anthropic_api_key")),
        "anthropic_api_key_masked": mask_api_key(s.get("anthropic_api_key", "")),
        "anthropic_api_key": s.get("anthropic_api_key", ""),
        "anthropic_model": s.get("anthropic_model"),
        "surcharge_night_pct": s.get("surcharge_night_pct"),
        "surcharge_sunday_pct": s.get("surcharge_sunday_pct"),
        "surcharge_holiday_pct": s.get("surcharge_holiday_pct"),
    }


@app.post("/api/settings")
def post_settings(req: SettingsUpdate) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if req.anthropic_api_key is not None:
        patch["anthropic_api_key"] = req.anthropic_api_key.strip()
    if req.anthropic_model is not None:
        patch["anthropic_model"] = req.anthropic_model.strip()
    for key in (
        "surcharge_night_pct", "surcharge_sunday_pct", "surcharge_holiday_pct"
    ):
        val = getattr(req, key)
        if val is not None:
            patch[key] = float(val)
    save_settings(patch)
    return {"ok": True}


@app.post("/api/settings/test")
def post_settings_test() -> dict[str, Any]:
    """Probe the configured API key with a cheap one-token request."""
    key = get_api_key()
    if not key:
        raise HTTPException(400, "Kein API-Key gesetzt.")
    try:
        client = Anthropic(api_key=key)
        client.messages.create(
            model=get_model(),
            max_tokens=4,
            messages=[{"role": "user", "content": "ping"}],
        )
    except Exception as exc:
        raise HTTPException(400, f"API-Key abgelehnt: {exc}") from exc
    return {"ok": True, "model": get_model()}


# ---------- Logo ----------

_LOGO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


@app.get("/api/settings/logo")
def get_logo():
    """Serve the stored logo, or 404 if none uploaded."""
    p = logo_path()
    if not p:
        raise HTTPException(404, "Kein Logo hochgeladen.")
    ext = p.suffix.lstrip(".")
    return Response(
        content=p.read_bytes(),
        media_type=_LOGO_MIME.get(ext, "image/png"),
    )


@app.post("/api/settings/logo")
async def post_logo(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and store a logo image (PNG/JPG/SVG/WebP, max 2 MB)."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lstrip(".").lower() or "png"
    if ext not in _LOGO_MIME:
        raise HTTPException(400, f"Dateiformat nicht unterstützt: .{ext}. Erlaubt: png, jpg, svg, webp")
    content = await file.read()
    if len(content) > _MAX_LOGO_BYTES:
        raise HTTPException(400, "Logo zu groß (max. 2 MB).")
    save_logo(content, ext)
    return {"ok": True, "ext": ext, "size": len(content)}


@app.delete("/api/settings/logo")
def del_logo() -> dict[str, Any]:
    """Remove the stored logo."""
    if not has_logo():
        raise HTTPException(404, "Kein Logo vorhanden.")
    delete_logo()
    return {"ok": True}


@app.get("/api/settings/logo/info")
def get_logo_info() -> dict[str, Any]:
    p = logo_path()
    if not p:
        return {"has_logo": False}
    return {"has_logo": True, "filename": p.name, "size": p.stat().st_size}


# ---------- Signature ----------

_SIG_MIME = {"png": "image/png", "webp": "image/webp"}
_MAX_SIG_BYTES = 2 * 1024 * 1024  # 2 MB


@app.get("/api/settings/signature")
def get_signature():
    """Serve the stored signature image, or 404 if none uploaded."""
    p = signature_path()
    if not p:
        raise HTTPException(404, "Keine Unterschrift hochgeladen.")
    ext = p.suffix.lstrip(".")
    return Response(
        content=p.read_bytes(),
        media_type=_SIG_MIME.get(ext, "image/png"),
    )


@app.post("/api/settings/signature")
async def post_signature(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a signature image (PNG/WebP with transparency, max 2 MB).

    A transparent-background PNG gives the cleanest result, since the image
    is stamped directly onto the protocol's bottom-left corner."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lstrip(".").lower() or "png"
    if ext not in _SIG_MIME:
        raise HTTPException(
            400,
            f"Dateiformat nicht unterstützt: .{ext}. Erlaubt: png, webp "
            "(am besten mit transparentem Hintergrund)",
        )
    content = await file.read()
    if len(content) > _MAX_SIG_BYTES:
        raise HTTPException(400, "Unterschrift zu groß (max. 2 MB).")
    save_signature(content, ext)
    return {"ok": True, "ext": ext, "size": len(content)}


@app.delete("/api/settings/signature")
def del_signature() -> dict[str, Any]:
    """Remove the stored signature."""
    if not has_signature():
        raise HTTPException(404, "Keine Unterschrift vorhanden.")
    delete_signature()
    return {"ok": True}


@app.get("/api/settings/signature/info")
def get_signature_info() -> dict[str, Any]:
    p = signature_path()
    if not p:
        return {"has_signature": False}
    return {
        "has_signature": True,
        "filename": p.name,
        "size": p.stat().st_size,
    }


# ---------- Skill ----------


@app.get("/api/skill")
def get_skill() -> dict[str, Any]:
    return {
        "content": load_skill(),
        "original": load_skill_original(),
    }


@app.post("/api/skill")
def post_skill(req: SkillSave) -> dict[str, Any]:
    if not req.content or not req.content.strip():
        raise HTTPException(400, "Skill-Inhalt ist leer.")
    save_skill(req.content)
    return {"ok": True}


@app.post("/api/skill/reset")
def post_skill_reset() -> dict[str, Any]:
    reset_skill()
    return {"ok": True, "content": load_skill()}


# ---------- Template ----------


@app.get("/api/template")
def get_template_info() -> dict[str, Any]:
    return {
        "positions": load_positions(),
        "template_url": "/api/template/pdf",
        "is_custom": TEMPLATE_PATH.exists(),
    }


@app.get("/api/template/pdf")
def get_template_pdf() -> FileResponse:
    return FileResponse(
        template_path(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="template.pdf"'},
    )


@app.get("/api/template/preview")
def get_template_preview() -> Response:
    """Render a fresh preview PDF with sample data, return bytes inline."""
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        stamp_preview(template_path(), load_positions(), tmp_path)
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="preview.pdf"'},
    )


@app.get("/api/template/preview.png")
def get_template_preview_png() -> Response:
    """PNG version of the preview — embedded inline in <img> elements, which
    works reliably across all browsers (unlike PDF iframes)."""
    import io
    from pdf2image import convert_from_path

    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        stamp_preview(template_path(), load_positions(), tmp_path)
        pages = convert_from_path(str(tmp_path), dpi=110, first_page=1,
                                  last_page=1)
        buf = io.BytesIO()
        pages[0].save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
    finally:
        tmp_path.unlink(missing_ok=True)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/template/upload")
async def post_template_upload(
    file: UploadFile = File(...),
    analyze: bool = True,
) -> dict[str, Any]:
    """Receive a PDF template, save it, optionally run Vision analysis."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Bitte PDF-Datei hochladen.")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Datei zu groß (>10 MB).")
    save_template_pdf(content)
    log.info("Template uploaded, size=%d bytes", len(content))

    result: dict[str, Any] = {
        "ok": True,
        "analyzed": False,
        "filename": file.filename,
    }

    if analyze:
        try:
            positions = analyze_template(TEMPLATE_PATH)
            save_positions(positions)
            result["analyzed"] = True
            result["positions"] = positions
        except Exception as exc:
            log.exception("Vision analysis failed")
            result["error"] = str(exc)

    return result


@app.post("/api/template/positions")
def post_positions(req: PositionsSave) -> dict[str, Any]:
    save_positions(req.positions)
    return {"ok": True}


@app.post("/api/template/reset")
def post_template_reset() -> dict[str, Any]:
    reset_template()
    return {"ok": True, "positions": load_positions()}


# ---------- Health ----------


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Static SPA — mounted last so /api routes take precedence
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
