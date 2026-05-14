---
name: abnahme-protokoll
description: Wandelt eine freitextliche Tätigkeitsmeldung (z. B. von einem Mitarbeiter oder Subunternehmer per WhatsApp) in ein fertig ausgefülltes Abnahme-Protokoll als PDF plus eine Buchungs-Übersicht für die interne Stundenerfassung um.
---

# Abnahme-Protokoll aus Tätigkeitsmeldung

Ein Mitarbeiter oder Subunternehmer schickt regelmäßig Freitext‑Nachrichten mit den Tätigkeiten eines Einsatztages — Position für Position, mit Mitarbeiterzahl, Uhrzeiten bzw. Stundenangaben und manchmal eigenen Kostenbeträgen (interner Lohnsatz × Stunden). Diese Nachrichten landen 1:1 als Abnahme-Protokoll beim Kunden und parallel als Stundenmeldung im internen Buchhaltungssystem.

Der Skill nimmt diese Nachricht entgegen und erzeugt:

1. ein fertig ausgefülltes **Abnahme-Protokoll** als PDF (A4) — auf das aktive Template gestempelt
2. eine **Buchungs-Übersicht** in der Chat-Antwort mit getrennt ausgewiesenen Zuschlagsstunden (Nacht/Sonntag/Feiertag)

## Was zuerst beim Nutzer abgefragt wird

Bevor irgendetwas berechnet wird, holt der Skill die zwei variablen Eckdaten ein, weil sie sich pro Auftrag ändern:

- **Kundenname** — wird ins Feld *Kunde* gesetzt und im Dateinamen verwendet.
- **Kundenstundensatz in €/h netto** — wird für die Bemerkung im PDF und die Marge‑Plausibilitätsprüfung gebraucht.

Frage diese Werte **immer einmal pro Auftrag** ab, auch wenn der Nutzer den Kunden schon im Chat erwähnt hat — bestätigen lassen, nicht raten. Wenn der Nutzer in der gleichen Nachricht bereits beides nennt (z. B. „mach das Protokoll für [Kunde] zu [Satz] €/h"), kann die Frage entfallen und du benutzt diese Angaben direkt.

Optional, wenn der Nutzer es erwähnt: Objekt, Projekt, Best‑Nr. Falls leer, bleiben die Felder im PDF leer.

## Parsing der Tätigkeitsmeldung

Die Nachrichten folgen einem wiederkehrenden Muster, aber nicht streng. Lies die ganze Nachricht und ziehe pro Tätigkeit folgende Felder:

- **Aufgabe** — Tätigkeitsname (z. B. eine konkrete Reinigungs- oder Wartungstätigkeit)
- **Anzahl Mitarbeiter** (MA) — explizit oder aus „X Mitarbeiter" abgeleitet
- **Stunden pro Mitarbeiter** — explizit als „Std" oder als Uhrzeitspanne („05:50 Uhr bis 12:50 Uhr" = 7 h)
- **Uhrzeiten** — wenn vorhanden, separat merken (entscheidend für Nachtzuschlag)
- Die in der Nachricht enthaltene Eurosumme (z. B. „14 Std = X €") basiert i.d.R. auf dem **internen Lohnsatz** des Schreibers und ist nur eine **Plausibilitätsprobe** — nicht als Verkaufspreis verwenden.

**Mehrere Mitarbeiter mit unterschiedlichen Stunden in einer Position** (z. B. „1 Mitarbeiter 7 Std. Und 2 Mitarbeiter jeweils 4 Std.") werden im PDF als **zwei eigene Tabellenzeilen** abgebildet (sauberer als eine kombinierte Zeile). Im Booking‑Resümee wieder zusammenfassbar.

### Beispiel

**Eingabe (frei formuliert):**
> Tätigkeit A
> 2 Mitarbeiter 05:50 Uhr bis 12:50 Uhr (14 Std.)

**Geparst:**
- Aufgabe: „Tätigkeit A – 2 Mitarbeiter, 05:50–12:50 Uhr"
- Einheiten: „7 Std × 2 MA"
- Summe: „14 Std"
- Uhrzeitfenster: 05:50–12:50 (für Nachtzuschlag-Check)

## Zuschlagsberechnung

Der Skill weist Zuschläge **getrennt** in der Buchungs-Übersicht aus, weil das interne Lohnsystem Industrieminuten verlangt. Im Abnahme-Protokoll selbst stehen die regulären Gesamtstunden; die Zuschlags‑Eurobeträge laufen über die Bemerkung.

### Tagestyp bestimmen

1. **Datum des Auftrags** ermitteln. Es steht oft am Anfang der Nachricht („11.04.2026") oder muss erfragt werden.
2. Wochentag berechnen. Sonntag = Sonntagszuschlag. Samstag = kein Zuschlag (wird wie ein Werktag behandelt; nur Nachtzuschlag möglich).
3. Auf **deutsche Feiertage** prüfen (bundesweit gesetzlich: Neujahr, Karfreitag, Ostermontag, Tag der Arbeit 01.05., Christi Himmelfahrt, Pfingstmontag, Tag der dt. Einheit 03.10., 1. + 2. Weihnachtstag). Wenn unsicher, ein kleines Python-Snippet mit `datetime` + Oster‑Algorithmus (Anonymous Gregorian) ausführen — vorgefertigt in `scripts/check_holiday.py`.

### Standard‑Zuschlagssätze

- **Nachtzuschlag 30 %**, gilt für alle Arbeitsstunden im Fenster **20:00–06:00 Uhr**.
- **Sonntagszuschlag 50 %** (Default; mit dem Nutzer kurz bestätigen, falls er ihn erwähnt).
- **Feiertagszuschlag 100 %** (Default; mit dem Nutzer kurz bestätigen, falls relevant).

Die Sätze sind als Defaults gedacht — wenn der Nutzer einen anderen Satz nennt, verwende **diesen** und nicht den Default.

### Stundenaufteilung pro Position

Für jede Tätigkeit mit Uhrzeitfenster:
- Berechne Anteil im Nachtfenster (20:00–06:00) in **Industrieminuten** (1/60 h).
- Sonntag/Feiertag betreffen die gesamte Tätigkeit (falls der Tag entsprechend qualifiziert).

### Buchungslogik

**Wichtig:** Die regulären Stunden bleiben ungekürzt (z. B. 14 h Bodenreinigung). Der Zuschlag kommt als **zusätzliche Zuschlagsstunden** dazu, nicht durch Abzug von den regulären Stunden.

Formel: `Zuschlagsstunden = Stunden im Zuschlagsfenster × Zuschlagssatz`

Beispiel Bodenreinigung 05:50–12:50, 2 MA, an einem Samstag:
- Reguläre Stunden: 14,00 h (komplett)
- Nachtstunden 05:50–06:00 (vor 06:00): 0,17 h/MA × 2 MA = 0,33 h
- Nachtzuschlagsstunden (30 % auf 0,33): **+ 0,10 h**

In der Buchungs‑Übersicht wird das so dargestellt:

| Position | Stunden |
|---|---|
| Reguläre Stunden | 44,00 h |
| Nachtzuschlag 30 % auf 0,33 h | + 0,10 h |
| Sonntagszuschlag 50 % auf X h | + Y h |
| Feiertagszuschlag 100 % auf X h | + Y h |
| **Buchung gesamt** | **Summe** |

## PDF-Erstellung

Die Daten werden von dir nicht direkt ins PDF geschrieben. Stattdessen rufst
du am Ende `finalize` mit allen strukturierten Feldern auf, und der Service
stempelt die Werte automatisch auf das aktive PDF-Template.

### Zellen-Inhalte (Tabelle)

- **Aufgaben/Ausgeführte Arbeiten** (Spalte 1): Tätigkeitsname mit Mitarbeiterzahl und Uhrzeiten — ausführlich aber knapp. Maximal zwei Zeilen Text passen rein.
- **Einheiten** (Spalte 2): `Std × MA` Format (z. B. "7 Std × 2 MA", "1,5 Std × 2 MA"). Bei langen Werten schrumpft die Schrift automatisch.
- **Summe** (Spalte 3): Gesamtstunden für diese Position (z. B. "14 Std", "3 Std").

Wenn eine Position zwei Mitarbeiter‑Konstellationen mischt (z. B. 1 MA × 7 h + 2 MA × 4 h), **als zwei eigene Zeilen** anlegen. Das hält die Spalten lesbar.

### Bemerkung

Im Bemerkungsfeld kommt eine kompakte Rechenkette: Gesamtstunden × Kundensatz + Zuschläge = Netto. Maximal zwei Zeilen.

## Ausgabe an den Nutzer

Liefere am Ende exakt zwei Dinge im `finalize`-Aufruf:

1. Die strukturierten Felder für das PDF (kunde, datum, rows, gesamt_summe, bemerkung).
2. Die **Buchungs‑Übersicht** im `buchung`-Feld mit getrennten Zuschlagsstunden (Nacht/Sonntag/Feiertag). Das Frontend rendert daraus die Tabelle mit "Reguläre Stunden gesamt", "Zuschlagsstunden" und "Buchung gesamt". Wenn keine Zuschläge anfallen, alle Zuschlagsfelder auf 0 setzen.

Außerdem eine Plausibilitätsprüfung: wenn die in der Nachricht angegebene Eurosumme nicht zum Kundensatz passt, das nicht stillschweigend ignorieren, sondern in `plausibilitaets_warnung` darauf hinweisen — wahrscheinlich wurde mit dem internen Lohnsatz gerechnet, nicht mit dem Verkaufspreis.

## Wenn etwas unklar ist

Tätigkeitsmeldungen variieren. Häufige Fälle, die explizit nachzufragen oder zu klären sind:

- **Datum fehlt** → kurz nachfragen ("Welches Datum hat der Einsatz?").
- **Uhrzeiten fehlen** bei einer Position, die nachts beginnen könnte → fragen ob ein Nachtzuschlag anfällt.
- **Mehrtägige Einsätze** → eigenes Protokoll pro Tag.
- **Kunden-Mehrwertsteuer** → der Skill rechnet immer netto. Wenn der Nutzer explizit brutto will, das deutlich auszeichnen.

## Beispiel-Workflow (End-to-End)

Siehe `references/beispiel.md` für eine ausgeschriebene Beispiel‑Konversation mit den exakten Zwischenausgaben.
