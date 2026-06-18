"""Generate the bundled generic AcroForm default template.

Run this to (re)produce ``template.pdf`` in this directory. The PDF is a
neutral Abnahme-Protokoll with named AcroForm text fields so the service's
default ``acroform`` mode works out of the box — no customer-specific
template required.

The field names produced here MUST match ``positions.json`` in this folder:

    header : kunde, objekt, projekt, best_nr, datum
    rows   : aufgabe_N, einheiten_N, summe_N   (N = 1..8)
    total  : gesamt
    remark : bemerkung_1, bemerkung_2

Usage:
    python -m app.default_template.build_default_template
    # or, from this directory:
    python build_default_template.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4  # 595.28 x 841.89
MARGIN = 56
ROW_COUNT = 8
ACCENT = HexColor("#0B6E7F")
LABEL = HexColor("#0E2A40")
GREY = HexColor("#888888")

OUT_PATH = Path(__file__).parent / "template.pdf"


def _field(c: canvas.Canvas, name: str, x: float, y: float, w: float,
           h: float = 16, size: int = 10) -> None:
    c.acroForm.textfield(
        name=name, x=x, y=y, width=w, height=h,
        borderWidth=0, fontName="Helvetica", fontSize=size,
        fillColor=white, textColor=black, forceBorder=False,
    )


def build(out_path: Path = OUT_PATH) -> Path:
    c = canvas.Canvas(str(out_path), pagesize=A4)

    # ---- Title ----
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGIN, PAGE_H - 70, "Abnahme-Protokoll")
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(MARGIN, PAGE_H - 80, PAGE_W - MARGIN, PAGE_H - 80)

    # ---- Header block ----
    header = [
        ("Kunde", "kunde"),
        ("Objekt", "objekt"),
        ("Projekt", "projekt"),
        ("Best.-Nr.", "best_nr"),
        ("Datum", "datum"),
    ]
    label_x = MARGIN
    field_x = MARGIN + 90
    field_w = 240
    y = PAGE_H - 115
    step = 26
    c.setFont("Helvetica", 10)
    for label, name in header:
        c.setFillColor(LABEL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(label_x, y + 3, label)
        _field(c, name, field_x, y, field_w)
        c.setStrokeColor(HexColor("#cccccc"))
        c.setLineWidth(0.5)
        c.line(field_x, y - 2, field_x + field_w, y - 2)
        y -= step

    # ---- Table ----
    table_top = y - 20
    col_aufgabe_x = MARGIN
    col_einheiten_x = MARGIN + 300
    col_summe_x = MARGIN + 390
    col_aufgabe_w = 290
    col_einheiten_w = 85
    col_summe_w = 90
    table_right = col_summe_x + col_summe_w

    # Table header
    c.setFillColor(ACCENT)
    c.rect(MARGIN, table_top, table_right - MARGIN, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(col_aufgabe_x + 4, table_top + 6, "Tätigkeit")
    c.drawString(col_einheiten_x + 4, table_top + 6, "Einheiten")
    c.drawString(col_summe_x + 4, table_top + 6, "Summe")

    # Table rows
    row_h = 26
    ry = table_top
    c.setStrokeColor(HexColor("#dddddd"))
    c.setLineWidth(0.5)
    for i in range(1, ROW_COUNT + 1):
        ry -= row_h
        c.line(MARGIN, ry, table_right, ry)
        _field(c, f"aufgabe_{i}", col_aufgabe_x + 4, ry + 6, col_aufgabe_w, size=9)
        _field(c, f"einheiten_{i}", col_einheiten_x + 4, ry + 6, col_einheiten_w, size=9)
        _field(c, f"summe_{i}", col_summe_x + 4, ry + 6, col_summe_w, size=9)
    # column separators
    for cx in (col_einheiten_x, col_summe_x):
        c.line(cx, ry, cx, table_top)
    c.rect(MARGIN, ry, table_right - MARGIN, table_top - ry, fill=0, stroke=1)

    # ---- Gesamt ----
    gy = ry - 28
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(col_einheiten_x - 60, gy + 4, "Gesamt:")
    _field(c, "gesamt", col_summe_x + 4, gy, col_summe_w, size=10)
    c.setStrokeColor(HexColor("#cccccc"))
    c.line(col_summe_x + 4, gy - 2, col_summe_x + 4 + col_summe_w, gy - 2)

    # ---- Bemerkung ----
    by = gy - 40
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, by + 4, "Bemerkung")
    _field(c, "bemerkung_1", MARGIN, by - 22, table_right - MARGIN, size=9)
    _field(c, "bemerkung_2", MARGIN, by - 44, table_right - MARGIN, size=9)
    c.setStrokeColor(HexColor("#cccccc"))
    c.line(MARGIN, by - 24, table_right, by - 24)
    c.line(MARGIN, by - 46, table_right, by - 46)

    # ---- Signature area (bottom-left) ----
    sig_y = 70
    c.setStrokeColor(GREY)
    c.setLineWidth(0.75)
    c.line(MARGIN, sig_y - 4, MARGIN + 200, sig_y - 4)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN, sig_y - 16, "Unterschrift")

    c.showPage()
    c.save()
    return out_path


if __name__ == "__main__":
    p = build()
    print(f"Wrote {p}")
