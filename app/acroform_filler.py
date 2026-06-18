"""Fill AcroForm text fields in a PDF template by writing values directly
into the form's /V entries and setting /NeedAppearances=true.

Why not stamp text as a graphic overlay?
  An overlay is viewer-agnostic but the resulting values are no longer
  editable — the user sees "ghost" text behind any corrections they type.
  Writing into form fields preserves full editability in Acrobat, Preview,
  Foxit, and any other standards-compliant viewer.

Why not use pypdf's update_page_form_field_values?
  It crashes on widgets without an /AP entry (common for buttons/checkboxes
  in many templates). We walk the widget annotations directly instead, touch
  only text fields (/FT=/Tx), strip stale /AP streams, and force appearance
  regeneration via /NeedAppearances=true.

Umlauts / appearance baking:
  We do NOT rely on /NeedAppearances (viewer-side appearance regeneration).
  Poppler — which our server-side preview uses (pdf2image) — drops umlauts
  (ä ö ü ß) and some special chars when it regenerates field appearances.
  Instead we BAKE the appearance streams ourselves via pypdf
  (update_page_form_field_values with auto_regenerate=False), so the glyphs
  are drawn explicitly and render identically in every viewer, poppler
  included. The fields stay editable (the /V values remain). We fall back to
  the /NeedAppearances approach only if baking raises.

Positions-config keys used by this module (under "mode": "acroform"):
  header_fields  : {logical_name: acroform_field_name, ...}
  row_fields     : {"1": [aufgabe_field, einheiten_field, summe_field], ...}
  gesamt_field   : acroform_field_name for the total units cell
  bemerkung_fields: [field_name_row1, field_name_row2, field_name_row3]
  bemerkung_chars_per_line: int (default 95)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _qualified_name(annot) -> str:
    """Return the fully-qualified field name for a widget annotation.

    Walks the /Parent chain and joins segment names with dots, e.g.
    "Text1.0.0.0" or "Kunde". This matches the naming convention that
    pypdf exposes and that template authors see in Acrobat's field list.
    """
    parts = []
    name = annot.get("/T")
    p = annot.get("/Parent")
    while p is not None:
        if hasattr(p, "get_object"):
            p = p.get_object()
        t = p.get("/T") if hasattr(p, "get") else None
        if t:
            parts.insert(0, str(t))
        p = p.get("/Parent") if hasattr(p, "get") else None
    if name:
        parts.append(str(name))
    return ".".join(parts)


def _set_da_size(annot, font_size: int) -> None:
    """Force an explicit font size in a widget's /DA.

    Many templates ship /DA with size 0 (auto-grow). Auto-grow makes baked
    appearances render comically large (the glyph is scaled to the field
    height), so we pin an explicit size before baking.
    """
    annot[NameObject("/DA")] = TextStringObject(f"/Helv {font_size} Tf 0 g")


def _set_field_needappearances(annot, value: str, font_size: int = 10) -> None:
    """Fallback writer: set /V + /DA and drop /AP so the viewer regenerates.

    Only used if appearance baking raises. Subject to the poppler umlaut bug,
    but better than no value at all.
    """
    annot[NameObject("/V")] = TextStringObject(str(value))
    _set_da_size(annot, font_size)
    if "/AP" in annot:
        del annot["/AP"]


def _text_widgets(page):
    """Yield the text-field (/FT=/Tx) widget annotations on a page."""
    annots = page.get("/Annots")
    if not annots:
        return
    if hasattr(annots, "get_object"):
        annots = annots.get_object()
    for annot_ref in annots:
        annot = annot_ref.get_object()
        if annot.get("/Subtype") != "/Widget":
            continue
        if annot.get("/FT") != "/Tx":
            continue  # skip buttons, checkboxes, signatures, etc.
        yield annot


def _wrap_text(text: str, chars_per_line: int, max_lines: int) -> list[str]:
    """Word-wrap text into at most max_lines lines of chars_per_line width."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if len(candidate) <= chars_per_line:
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_field_map(positions: dict[str, Any], data: dict[str, Any]) -> dict[str, tuple[str, int]]:
    """Translate a logical data dict into a flat {acroform_field: (value, font_size)} map.

    positions must follow the "mode": "acroform" schema described in the
    module docstring. Unknown or empty values are silently skipped.
    """
    field_map: dict[str, tuple[str, int]] = {}

    # Header fields
    for logical, field_name in (positions.get("header_fields") or {}).items():
        val = data.get(logical)
        if val:
            field_map[field_name] = (str(val), 11)

    # Table rows  {"1": [aufgabe_field, einheiten_field, summe_field], ...}
    # Rows are matched by position (1-based). An explicit "row" key in the
    # dict overrides the positional index — useful if Claude skips rows.
    row_fields = positions.get("row_fields") or {}
    for enum_idx, row_data in enumerate(data.get("rows") or [], start=1):
        if isinstance(row_data, dict):
            row_idx = str(row_data.get("row", enum_idx))
            aufgabe = row_data.get("aufgabe", "")
            einheiten = row_data.get("einheiten", "")
            summe = row_data.get("summe", "")
        else:
            # List form: [aufgabe, einheiten, summe]
            parts = list(row_data) + ["", "", ""]
            aufgabe, einheiten, summe = parts[0], parts[1], parts[2]
            row_idx = str(enum_idx)

        col = row_fields.get(row_idx)
        if col and len(col) >= 3:
            if aufgabe:
                field_map[col[0]] = (str(aufgabe), 9)
            if einheiten:
                field_map[col[1]] = (str(einheiten), 10)
            if summe:
                field_map[col[2]] = (str(summe), 10)

    # Einheiten-Gesamt total cell
    gesamt_field = positions.get("gesamt_field")
    gesamt_val = data.get("gesamt_summe")
    if gesamt_field and gesamt_val:
        field_map[gesamt_field] = (str(gesamt_val), 11)

    # Bemerkung: split across multiple fields if configured
    bem_fields: list[str] = positions.get("bemerkung_fields") or []
    chars = int(positions.get("bemerkung_chars_per_line", 95))
    bem_text = data.get("bemerkung") or ""
    if bem_fields and bem_text:
        lines = _wrap_text(bem_text, chars, max_lines=len(bem_fields))
        for field_name, line in zip(bem_fields, lines):
            field_map[field_name] = (line, 10)

    return field_map


def fill_acroform(
    template_path: str | Path,
    positions: dict[str, Any],
    data: dict[str, Any],
    out_path: str | Path,
) -> None:
    """Fill AcroForm fields in template_path with data and write to out_path.

    The output PDF keeps all form fields editable in any standards-compliant viewer.

    Args:
        template_path: Path to the AcroForm PDF template.
        positions: Positions config dict with mode="acroform" schema.
        data: Logical data dict (kunde, objekt, datum, rows, bemerkung, …).
        out_path: Destination path for the filled PDF.
    """
    template_path = Path(template_path)
    out_path = Path(out_path)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    field_map = build_field_map(positions, data)
    if not field_map:
        log.warning("acroform_filler: field_map is empty — no fields will be written")

    reader = PdfReader(str(template_path))
    writer = PdfWriter(clone_from=reader)

    # Pin an explicit font size on every target field's /DA before baking,
    # otherwise size-0 (auto-grow) fields render huge in the baked appearance.
    filled: set[str] = set()
    for page in writer.pages:
        for annot in _text_widgets(page):
            qname = _qualified_name(annot)
            if qname in field_map:
                _set_da_size(annot, field_map[qname][1])
                filled.add(qname)

    missing = set(field_map) - filled
    if missing:
        log.warning("acroform_filler: fields not found in template: %s", missing)

    # Bake appearance streams ourselves (auto_regenerate=False) so umlauts and
    # special chars render correctly in every viewer, including poppler — which
    # drops them when it regenerates appearances from /NeedAppearances.
    flat = {qname: value for qname, (value, _size) in field_map.items()}
    baked = True
    try:
        for page in writer.pages:
            writer.update_page_form_field_values(
                page, flat, auto_regenerate=False
            )
    except Exception:
        baked = False
        log.exception(
            "acroform_filler: appearance baking failed — "
            "falling back to /NeedAppearances"
        )

    if not baked:
        # Fallback: write /V directly and force viewer-side regeneration.
        root = writer._root_object
        if "/AcroForm" in root:
            root["/AcroForm"].update({
                NameObject("/NeedAppearances"): BooleanObject(True),
            })
        for page in writer.pages:
            for annot in _text_widgets(page):
                qname = _qualified_name(annot)
                if qname in field_map:
                    value, font_size = field_map[qname]
                    _set_field_needappearances(annot, value, font_size=font_size)

    with open(out_path, "wb") as f:
        writer.write(f)

    log.info(
        "acroform_filler: wrote %s (%d fields, baked=%s)",
        out_path.name, len(filled), baked,
    )
