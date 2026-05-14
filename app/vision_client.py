"""Use Claude Vision to derive PDF-field coordinates from an uploaded template.

Workflow:
1. Render the first page of the template PDF as a PNG at known DPI.
2. Send the image to Claude with a tightly scoped prompt that asks for the
   field rectangles (in image pixels) of: kunde/objekt/projekt/best_nr/datum,
   the first row baseline + row step for the work table, table column x/w,
   the einheiten-gesamt cell, and the bemerkung box.
3. Convert pixel coords to PDF points using DPI -> 72 ratio.
4. Return a positions.json dict compatible with pdf_stamper.

The image gets a small grid + axis ruler burned in to help the model align.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path

from .settings_store import get_api_key, get_model

log = logging.getLogger(__name__)

ANALYZE_DPI = 150  # higher = better precision, more tokens
PT_PER_INCH = 72.0


def _render_first_page(pdf_path: Path, dpi: int = ANALYZE_DPI) -> Image.Image:
    """Render page 1 of the PDF as a PIL image."""
    pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=1, last_page=1)
    if not pages:
        raise RuntimeError("Could not render template PDF.")
    return pages[0].convert("RGB")


def _add_grid(img: Image.Image, step_px: int = 50) -> Image.Image:
    """Burn a subtle gray grid + axis labels onto the image."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12
        )
    except Exception:
        font = ImageFont.load_default()

    grid_color = (200, 200, 200)
    label_color = (100, 100, 100)

    for x in range(0, w, step_px):
        draw.line([(x, 0), (x, h)], fill=grid_color, width=1)
        if x > 0:
            draw.text((x + 2, 2), str(x), fill=label_color, font=font)
    for y in range(0, h, step_px):
        draw.line([(0, y), (w, y)], fill=grid_color, width=1)
        if y > 0:
            draw.text((2, y + 2), str(y), fill=label_color, font=font)
    return out


def _image_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


VISION_PROMPT = """Du analysierst eine PDF-Vorlage für ein Abnahme-Protokoll.
Das Bild zeigt die erste Seite mit einem hellgrauen 50-Pixel-Raster mit
Pixel-Koordinaten (Ursprung oben-links, x nach rechts, y nach unten).

Identifiziere die folgenden Felder und liefere **PIXEL-Koordinaten** als JSON.
Wichtig: y ist die **Text-Baseline** (Unterkante der normalen Buchstaben, OHNE
Unterlängen wie bei p, g), nicht die obere Kante der Zeile.

Zu identifizieren:

1. Daten-Felder (Eingabe-Linien rechts neben den Labels):
   - kunde, objekt, projekt, best_nr, datum
   - Pro Feld: x (linker Anfang der Eingabe), y (Baseline), w (Linienbreite)

2. Arbeitstabelle (3 Spalten: Aufgaben | Einheiten | Summe):
   - first_row_baseline_top: y-Baseline für die OBERSTE Textzeile in der
     ERSTEN Datenzeile (Spalte „Aufgaben" ist 2-zeilig — top = obere Zeile)
   - first_row_baseline_center: y-Baseline für vertikal zentrierten Text
     in derselben ersten Datenzeile (für Spalten Einheiten/Summe)
   - row_step: Pixel-Abstand zwischen aufeinanderfolgenden Datenzeilen
   - row_count: Anzahl der Datenzeilen (typisch 8)
   - col1: x, w (für die Aufgaben-Spalte, mit 2 Zeilen Wrapping)
   - col2: x, w (für die Einheiten-Spalte, zentriert)
   - col3: x, w (für die Summen-Spalte, zentriert)
   - gesamt: { y (baseline), x, w } für die „Einheiten gesamt"-Summen-Zelle

3. Bemerkungs-Feld (großer Textkasten unter der Tabelle):
   - x, y (baseline der ersten Textzeile), w

Liefere AUSSCHLIESSLICH ein JSON-Objekt im folgenden Schema, ohne Markdown,
ohne Erklärtext:

{
  "image_width_px": <int>,
  "image_height_px": <int>,
  "fields": {
    "kunde":   {"x": <int>, "y": <int>, "w": <int>},
    "objekt":  {"x": <int>, "y": <int>, "w": <int>},
    "projekt": {"x": <int>, "y": <int>, "w": <int>},
    "best_nr": {"x": <int>, "y": <int>, "w": <int>},
    "datum":   {"x": <int>, "y": <int>, "w": <int>}
  },
  "table": {
    "first_row_baseline_top": <int>,
    "first_row_baseline_center": <int>,
    "row_step": <int>,
    "row_count": <int>,
    "col1": {"x": <int>, "w": <int>},
    "col2": {"x": <int>, "w": <int>},
    "col3": {"x": <int>, "w": <int>},
    "gesamt": {"x": <int>, "y": <int>, "w": <int>}
  },
  "bemerkung": {"x": <int>, "y": <int>, "w": <int>}
}

Wenn ein Feld nicht eindeutig identifizierbar ist (z.B. die Vorlage hat
kein „Best-Nr."), setze den Wert auf null.
"""


def analyze_template(pdf_path: str | Path) -> dict[str, Any]:
    """Analyze a template PDF, return a positions.json-compatible dict.

    Raises on any failure (so the caller can show an error and keep the
    previous positions file untouched).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. Bitte erst in den "
            "Einstellungen hinterlegen."
        )

    # Render and annotate
    img = _render_first_page(pdf_path, ANALYZE_DPI)
    img_grid = _add_grid(img, step_px=50)
    img_b64 = _image_to_b64(img_grid)
    px_w, px_h = img.size

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=get_model(),
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    # Trim potential code fences
    if text.startswith("```"):
        text = text.strip("`")
        # remove leading "json\n" if present
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        pixel_data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.error("Vision returned non-JSON: %s", text[:500])
        raise RuntimeError(
            "Vision-Modell hat kein gültiges JSON geliefert."
        ) from exc

    # Convert px -> PDF points using the image DPI
    return _px_to_points(pixel_data, ANALYZE_DPI, px_w, px_h)


def _px_to_points(
    px_data: dict[str, Any], dpi: int, img_w: int, img_h: int
) -> dict[str, Any]:
    """Convert pixel coordinates (top-left origin) to PDF points (bottom-left).

    Pixel -> PDF point: scale = 72/dpi.
    Pixel y is from top; PDF y is from bottom => pdf_y = pdf_h - (px_y * scale)
    """
    scale = PT_PER_INCH / dpi
    page_w = img_w * scale
    page_h = img_h * scale

    def xy(field: dict[str, Any] | None) -> dict[str, Any] | None:
        if not field:
            return None
        out = {}
        if field.get("x") is not None:
            out["x"] = round(field["x"] * scale, 2)
        if field.get("y") is not None:
            out["y"] = round(page_h - field["y"] * scale, 2)
        if field.get("w") is not None:
            out["w"] = round(field["w"] * scale, 2)
        if field.get("h") is not None:
            out["h"] = round(field["h"] * scale, 2)
        return out

    out: dict[str, Any] = {
        "page_width": round(page_w, 2),
        "page_height": round(page_h, 2),
        "fields": {},
    }
    for key, fld in (px_data.get("fields") or {}).items():
        conv = xy(fld)
        if conv:
            conv.setdefault("size", 10)
            conv.setdefault("align", "left")
            out["fields"][key] = conv

    tbl_in = px_data.get("table") or {}
    if tbl_in:
        tbl_out: dict[str, Any] = {
            "row_count": int(tbl_in.get("row_count") or 8),
            "row_step": round((tbl_in.get("row_step") or 21) * scale, 2),
        }
        for k in ("first_row_baseline_top", "first_row_baseline_center"):
            if tbl_in.get(k) is not None:
                tbl_out[k] = round(page_h - tbl_in[k] * scale, 2)
        for col_key, defaults in [
            ("col1", {"size": 9, "align": "left",
                      "wrap_lines": 2, "line_height": 9.92}),
            ("col2", {"size": 9, "align": "center"}),
            ("col3", {"size": 9, "align": "center"}),
        ]:
            c = tbl_in.get(col_key) or {}
            conv = xy(c)
            if conv:
                conv.update(defaults)
                tbl_out[col_key] = conv
        g = xy(tbl_in.get("gesamt"))
        if g:
            g.update({"size": 10, "align": "center", "bold": True})
            tbl_out["gesamt"] = g
        out["table"] = tbl_out

    bem = xy(px_data.get("bemerkung"))
    if bem:
        bem.update({
            "size": 9, "align": "left",
            "wrap_lines": 2, "line_height": 11.34,
        })
        out["bemerkung"] = bem

    return out
