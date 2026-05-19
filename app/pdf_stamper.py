"""Stamp data fields onto a template PDF.

Two modes are supported, selected by positions["mode"]:

  "overlay" (default)
      Renders an invisible ReportLab overlay with the dynamic text at
      pixel-precise coordinates and merges it onto the template page.
      Works with any PDF — no AcroForm required.  Values are not editable
      after stamping.

  "acroform"
      Writes values directly into the template's AcroForm text fields and
      sets /NeedAppearances=true so the viewer regenerates appearances.
      Requires an AcroForm PDF and field-name mappings in positions config.
      Values remain fully editable in Acrobat / Preview / Foxit.
      See app/acroform_filler.py for config schema and implementation.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import black
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

log = logging.getLogger(__name__)


def _wrap(text: str, max_w: float, font: str, size: float,
          max_lines: int = 2) -> list[str]:
    """Word-wrap text into up to max_lines lines fitting max_w."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if stringWidth(candidate, font, size) <= max_w:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _draw_text(c: canvas.Canvas, text: str, field: dict[str, Any],
               font: str = "Helvetica") -> None:
    """Draw text into a field rectangle, honoring alignment + auto-shrink."""
    if not text:
        return
    size = float(field.get("size", 9))
    align = field.get("align", "left")
    x = float(field["x"])
    y = float(field["y"])
    w = float(field.get("w", 100))

    # Auto-shrink single-line text if it doesn't fit
    min_size = 6
    while size > min_size and stringWidth(text, font, size) > w:
        size -= 0.5

    c.setFont(font, size)
    c.setFillColor(black)
    if align == "center":
        c.drawCentredString(x + w / 2, y, text)
    elif align == "right":
        c.drawRightString(x + w, y, text)
    else:
        c.drawString(x, y, text)


def _draw_wrapped(c: canvas.Canvas, text: str, field: dict[str, Any],
                  font: str = "Helvetica",
                  line_h_override: float | None = None) -> None:
    """Draw a multi-line text into a field box (left-aligned)."""
    if not text:
        return
    size = float(field.get("size", 9))
    x = float(field["x"])
    y = float(field["y"])
    w = float(field.get("w", 100))
    max_lines = int(field.get("wrap_lines", 2))
    line_h = line_h_override if line_h_override is not None else size * 1.2

    lines = _wrap(text, w, font, size, max_lines=max_lines)
    c.setFont(font, size)
    c.setFillColor(black)
    # y refers to baseline of the FIRST line (top line in box)
    for i, ln in enumerate(lines):
        c.drawString(x, y - i * line_h, ln)


def _make_overlay(positions: dict[str, Any], data: dict[str, Any]) -> bytes:
    """Build the overlay PDF as raw bytes."""
    buf = io.BytesIO()
    page_w = float(positions.get("page_width", A4[0]))
    page_h = float(positions.get("page_height", A4[1]))
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # Header fields
    fields = positions.get("fields", {})
    for key in ("kunde", "objekt", "projekt", "best_nr", "datum"):
        if key in fields:
            _draw_text(c, str(data.get(key, "")), fields[key])

    # Table rows
    table = positions.get("table") or {}
    if table:
        rows = data.get("rows", [])
        baseline_top = float(table["first_row_baseline_top"])
        baseline_ctr = float(table.get(
            "first_row_baseline_center", baseline_top))
        step = float(table["row_step"])
        row_count = int(table.get("row_count", 8))
        col1 = table["col1"]
        col2 = table["col2"]
        col3 = table["col3"]
        col1_line_h = float(col1.get("line_height", col1.get("size", 9) * 1.2))

        for i, row in enumerate(rows[:row_count]):
            top_y = baseline_top - i * step
            ctr_y = baseline_ctr - i * step
            if isinstance(row, dict):
                task = row.get("aufgabe", "")
                einh = row.get("einheiten", "")
                summe = row.get("summe", "")
            else:
                task, einh, summe = row

            _draw_wrapped(c, task, {**col1, "y": top_y},
                          line_h_override=col1_line_h)
            _draw_text(c, str(einh), {**col2, "y": ctr_y})
            _draw_text(c, str(summe), {**col3, "y": ctr_y})

        # Einheiten-Gesamt-Summe
        gesamt_summe = data.get("gesamt_summe", "")
        if gesamt_summe and "gesamt" in table:
            _draw_text(c, str(gesamt_summe), table["gesamt"],
                       font="Helvetica-Bold")

    # Bemerkung
    bem = positions.get("bemerkung")
    if bem:
        bem_line_h = float(bem.get("line_height", bem.get("size", 9) * 1.2))
        _draw_wrapped(c, data.get("bemerkung", ""), bem,
                      line_h_override=bem_line_h)

    c.showPage()
    c.save()
    return buf.getvalue()


def stamp_pdf(
    template_pdf_path: str | Path,
    positions: dict[str, Any],
    data: dict[str, Any],
    out_path: str | Path,
) -> None:
    """Stamp dynamic data onto a copy of the template PDF.

    Dispatches to the AcroForm filler when positions["mode"] == "acroform",
    otherwise uses the ReportLab overlay approach.
    """
    if positions.get("mode") == "acroform":
        from .acroform_filler import fill_acroform
        fill_acroform(template_pdf_path, positions, data, out_path)
        return

    template_pdf_path = Path(template_pdf_path)
    out_path = Path(out_path)

    if not template_pdf_path.exists():
        raise FileNotFoundError(f"Template not found: {template_pdf_path}")

    overlay_bytes = _make_overlay(positions, data)
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
    template_reader = PdfReader(str(template_pdf_path))

    writer = PdfWriter()
    base_page = template_reader.pages[0]
    overlay_page = overlay_reader.pages[0]
    base_page.merge_page(overlay_page)
    writer.add_page(base_page)

    with open(out_path, "wb") as f:
        writer.write(f)


def stamp_preview(
    template_pdf_path: str | Path,
    positions: dict[str, Any],
    out_path: str | Path,
) -> None:
    """Stamp dummy sample data so the user can visually verify positions.

    Uses generic placeholders only — no real customer names, business
    details, or hourly rates appear in the rendered output.

    For acroform mode the preview is built from the header_fields and
    row_fields keys declared in positions, so every configured field gets
    a placeholder value regardless of template-specific field names.
    """
    if positions.get("mode") == "acroform":
        _stamp_acroform_preview(template_pdf_path, positions, out_path)
        return

    sample = {
        "kunde": "Beispiel-Kunde",
        "objekt": "Standort A",
        "projekt": "Projekt 1",
        "best_nr": "0000",
        "datum": "01.01.2026",
        "rows": [
            {"aufgabe": "Tätigkeit 1 – 2 Personen",
             "einheiten": "4 Std × 2 P", "summe": "8 Std"},
            {"aufgabe": "Tätigkeit 2",
             "einheiten": "5 Std × 1 P", "summe": "5 Std"},
            {"aufgabe": "Tätigkeit 3",
             "einheiten": "3 Std × 2 P", "summe": "6 Std"},
            {"aufgabe": "Tätigkeit 4",
             "einheiten": "2 Std × 1 P", "summe": "2 Std"},
        ],
        "gesamt_summe": "21 Std",
        "bemerkung": "Beispiel-Bemerkung zur Positions-Prüfung der PDF-Vorlage.",
    }
    stamp_pdf(template_pdf_path, positions, sample, out_path)


def _stamp_acroform_preview(
    template_pdf_path: str | Path,
    positions: dict[str, Any],
    out_path: str | Path,
) -> None:
    """Build a preview for acroform-mode templates using generic placeholders."""
    from .acroform_filler import fill_acroform

    # Build sample rows from however many row_fields are configured
    row_fields: dict = positions.get("row_fields") or {}
    sample_rows = [
        {
            "row": str(idx),
            "aufgabe": f"Tätigkeit {idx}",
            "einheiten": f"{idx} Std",
            "summe": f"{idx} Std",
        }
        for idx in sorted(row_fields.keys(), key=lambda k: int(k) if k.isdigit() else 0)[:4]
    ]

    # Build header sample from configured header_fields keys
    header_fields: dict = positions.get("header_fields") or {}
    sample_header = {
        "kunde": "Beispiel-Kunde",
        "objekt": "Standort A",
        "projekt": "Projekt 1",
        "best_nr": "0000",
        "datum": "01.01.2026",
    }
    # Include any extra header keys the template defines
    for logical in header_fields:
        if logical not in sample_header:
            sample_header[logical] = f"[{logical}]"

    sample = {
        **sample_header,
        "rows": sample_rows,
        "gesamt_summe": f"{len(sample_rows)} Std",
        "bemerkung": "Beispiel-Bemerkung zur Prüfung der Formularfelder.",
    }
    fill_acroform(template_pdf_path, positions, sample, out_path)
