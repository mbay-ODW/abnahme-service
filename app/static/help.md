# Hilfe

Diese Seite erklärt alle Funktionen des Service. Für Setup-, Deployment-
oder API-Details siehe die `README.md` im Repo.

## Workflow

1. WhatsApp-Nachricht in das Textfeld auf der Hauptseite einfügen.
2. **Protokoll erstellen** klicken.
3. Bei Bedarf werden Kunde und Stundensatz nachgefragt (entfällt, wenn die
   Nachricht das schon enthält oder der Kunde bereits bekannt ist).
4. Das fertige PDF und die Buchungs-Übersicht erscheinen.

Kunden, die einmal mit einem Stundensatz verarbeitet wurden, werden beim
nächsten Mal automatisch erkannt und der Satz wird vorgeschlagen.

## Tab „Allgemein"

### Anthropic API-Key

Dein persönlicher API-Key von
[console.anthropic.com](https://console.anthropic.com). Wird nur lokal in
`settings.json` gespeichert.

**Tipp**: Setz auf der Anthropic-Console ein Spending-Limit (Settings →
Limits), z. B. 20 €/Monat. So kann ein Fehler nie unbemerkt das Konto
leerlaufen.

### Modell

- **Sonnet 4.6** (Default): schnell, günstig, präzise genug für die meisten
  Fälle. ~2–5 Cent pro Protokoll.
- **Opus 4.7**: deutlich teurer, lohnt sich nur, wenn Sonnet bei
  besonders konfusen Nachrichten daneben liegt.
- **Haiku 4.5**: sehr günstig, aber Genauigkeit reicht für komplexere
  Hasan-Nachrichten oft nicht. Eher für Tests.

Modellwechsel wirkt sofort, kein Neustart nötig.

### Zuschlagssätze

Standard-Prozentsätze für Nacht-, Sonntags- und Feiertagsarbeit. Werden
in den Skill als Defaults eingespeist. Wenn die WhatsApp-Nachricht
explizit einen anderen Satz nennt, hat dieser Vorrang.

### API-Key testen

Schickt einen Mini-Request an Anthropic und prüft, ob der Key gültig
ist und das gewählte Modell verfügbar ist. Kostet weniger als 1 Cent.

## Tab „Skill"

Der **Skill-Prompt** ist die Anweisung, die Claude bei jeder Verarbeitung
erhält. Er enthält:

- Wie WhatsApp-Nachrichten zu parsen sind
- Wie Tabellenzeilen zusammenzustellen sind (z. B. mehrere Mitarbeiter
  mit unterschiedlichen Stunden als getrennte Zeilen)
- Zuschlagsberechnung (Nacht 20:00–06:00, Sonntag, Feiertag)
- Plausibilitäts-Check (z. B. erkennen, wenn die WhatsApp-Eurosumme auf
  dem internen Lohnsatz statt dem Kundensatz basiert)
- Output-Format

### Bearbeiten

Direkt im Markdown-Editor. Änderungen werden mit **Skill speichern** ins
Volume geschrieben und wirken ab dem nächsten Process-Call.

### Diff anzeigen

Zeigt zeilenweise, was du gegenüber der Original-Auslieferung geändert
hast. `-`-Zeilen sind aus dem Original entfernt, `+`-Zeilen neu.

### Auf Original zurücksetzen

Stellt die ausgelieferte Version wieder her. Deine Änderungen gehen
**unwiderruflich** verloren — vorher rauskopieren, wenn du sie behalten
willst.

### ⚠️ Vorsicht

Ein kaputter Skill bringt den Service nicht zum Absturz, aber kann das
Verhalten unbeabsichtigt ändern (z. B. falsche Stundenberechnung,
fehlende Felder). Bei seltsamen Ergebnissen → erst Skill prüfen, dann
ggf. zurücksetzen.

## Tab „PDF-Vorlage"

Die Vorlage besteht aus zwei Teilen:

1. Das **PDF** selbst — das visuelle Layout (Logo, Tabelle, Footer).
2. Die **Positions-Konfiguration** (`positions.json`) — sagt dem Service,
   an welchen Koordinaten welcher Wert hingestempelt werden soll.

### Eigene Vorlage hochladen

PDF in die Drop-Zone ziehen oder „Datei wählen" klicken. Maximal 10 MB,
A4 empfohlen.

Beim Upload wird automatisch **Claude Vision** benutzt, um die
Feld-Koordinaten zu erkennen. Das dauert ein paar Sekunden und kostet
~5–15 Cent.

### Vorschau prüfen

Direkt unter der Drop-Zone siehst du die aktuelle Vorlage mit
Beispieldaten (Mustermann GmbH, fiktive Tätigkeiten). So kannst du
prüfen, ob die Positionen sitzen.

Liegt etwas daneben, hast du zwei Möglichkeiten:

- Vorlage **nochmal hochladen** (kostet noch mal Vision-Aufruf).
- Tab **Positionen als JSON** öffnen und Koordinaten manuell anpassen.

### Erwartete Felder

Das Template muss diese Bereiche haben:

| Feld | Beschreibung |
|---|---|
| `kunde`, `objekt`, `projekt`, `best_nr`, `datum` | Einzeilige Felder im Kopfbereich |
| Tabelle (8 Zeilen) | 3 Spalten: Aufgaben (2-zeilig), Einheiten, Summe |
| `gesamt` | Summe aller Stunden, rechts unten in der Tabelle |
| `bemerkung` | 2-zeiliger Freitext unter der Tabelle |

### Positionen als JSON (Fallback-Editor)

Direkter Zugriff auf `positions.json`. Aufgeklappt zeigt es die aktuelle
Konfiguration:

```json
{
  "page_width": 595.27,
  "page_height": 841.89,
  "fields": {
    "kunde":   { "x": 127.6, "y": 742.68, "w": 212.6, "size": 10, "align": "left" },
    ...
  },
  "table": {
    "first_row_baseline_top": 561.26,
    "row_step": 21.26,
    ...
  },
  "bemerkung": { "x": 76.5, "y": 348.66, "w": 442.2, ... }
}
```

**Koordinatensystem**: PDF-Punkte, Ursprung **unten links** (ReportLab-
Convention). `y`-Werte sind die **Text-Baseline** (Unterkante normaler
Buchstaben, ohne Unterlängen).

Nach „JSON speichern" aktualisiert sich die Vorschau automatisch.

### Default wiederherstellen

Setzt sowohl PDF als auch Positionen auf die mit dem Image
ausgelieferte Default-Version zurück.

## Datenspeicherung

Alle Daten liegen im Mount-Verzeichnis des Containers (siehe `DATA_DIR`):

- `pdfs/` — alle erzeugten Protokolle, dauerhaft
- `settings.json` — API-Key, Modell, Zuschläge
- `skill.md` — aktiver Skill
- `skill.original.md` — Original für Reset/Diff
- `template.pdf` + `positions.json` — aktuelle Vorlage
- `customers.json` — Kunden-Memory

Bei Container-Updates bleiben alle deine Editierungen erhalten. Nur
fehlende Dateien werden aus dem Image ergänzt.

## Kosten im Überblick

- **Verarbeitung pro Protokoll**: ~2–5 Cent mit Sonnet 4.6
- **Template-Upload mit Vision**: ~5–15 Cent (einmalig pro neuer Vorlage)
- **API-Key-Test**: ~0,1 Cent

Bei ~10 Protokollen pro Woche bleibst du unter 5 € im Monat.

## Häufige Fragen

**Was, wenn die WhatsApp-Nachricht das Datum nicht enthält?**
Das UI fragt dich. Pflichtfeld.

**Was, wenn die Eurosumme der Nachricht nicht zum Kundensatz passt?**
Du bekommst eine Warnung im Ergebnis. Das passiert typisch, wenn die
Nachricht den **internen** Lohnsatz hochgerechnet hat statt den
Verkaufspreis.

**Mehrere Mitarbeiter mit unterschiedlichen Stunden in einer Position?**
Werden als getrennte Tabellenzeilen abgebildet (z. B. „1 MA × 7 h"
und „2 MA × 4 h" werden zwei Zeilen).

**Mehrtägige Einsätze?**
Aktuell ein Protokoll pro Tag. Schick die Nachrichten getrennt.

**Brutto oder netto?**
Standardmäßig netto. Wenn die Nachricht explizit Brutto sagt, wird das
in der Bemerkung kenntlich gemacht.
