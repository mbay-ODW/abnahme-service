# Abnahme-Service

WhatsApp-Tätigkeitsmeldung → ausgefülltes Abnahme-Protokoll (PDF) +
Buchungs-Übersicht für die interne Stundenerfassung.

Geschäftslogik (Skill), PDF-Vorlage und Verhalten sind über ein Web-UI
konfigurierbar; alle Daten werden lokal in einem Mount-Verzeichnis
persistiert.

---

## Inhalt

1. [Was der Service kann](#was-der-service-kann)
2. [Wie es funktioniert (Workflow)](#wie-es-funktioniert-workflow)
3. [Settings-Bereich](#settings-bereich)
   - [Tab „Allgemein"](#tab-allgemein)
   - [Tab „Skill"](#tab-skill)
   - [Tab „PDF-Vorlage"](#tab-pdf-vorlage)
4. [Datenpersistenz](#datenpersistenz)
5. [Deployment](#deployment)
   - [Variante 1: native (Python)](#variante-1-native-python)
   - [Variante 2: Docker (einzelner Container)](#variante-2-docker-einzelner-container)
   - [Variante 3: Docker Compose ohne Traefik](#variante-3-docker-compose-ohne-traefik)
   - [Variante 4: Docker Compose mit Traefik + Authelia](#variante-4-docker-compose-mit-traefik--authelia)
6. [Erste Schritte nach dem Deploy](#erste-schritte-nach-dem-deploy)
7. [Updates](#updates)
8. [Troubleshooting](#troubleshooting)
9. [Kosten](#kosten)
10. [API-Referenz](#api-referenz)

---

## Was der Service kann

- **Freitext-Parsing**: WhatsApp-Nachrichten (Tätigkeiten, Uhrzeiten,
  Mitarbeiterzahl, Stundenangaben) werden automatisch in strukturierte Daten
  umgewandelt.
- **Zuschlagsberechnung**: Nacht-, Sonntags- und Feiertagszuschläge werden
  pro Position auf Industrieminuten genau berechnet.
- **PDF-Generierung**: Fertig ausgefülltes Abnahme-Protokoll im A4-Format,
  mit konfigurierbarer Vorlage.
- **Buchungs-Übersicht**: getrennt nach regulären Stunden und Zuschlägen für
  die interne Lohnbuchhaltung.
- **Kunden-Memory**: bekannte Kunden mit Stundensätzen werden vorgeschlagen.
- **Plausibilitäts-Check**: erkennt typische Fehler (z. B. wenn die
  Eurosumme der WhatsApp-Nachricht auf dem internen Lohnsatz statt dem
  Kundensatz basiert).
- **Web-UI** mit drei Stages: Paste → ggf. Eingaben → Ergebnis.

## Wie es funktioniert (Workflow)

1. Du fügst die WhatsApp-Nachricht in das Textfeld ein und klickst
   **Protokoll erstellen**.
2. Der Service schickt den Text + den Skill-Prompt an die Anthropic-API.
   Claude analysiert die Nachricht, ruft im Hintergrund Python-Tools auf
   für die deterministische Berechnung (Industrieminuten im Nachtfenster,
   Feiertagsprüfung).
3. Wenn Kundenname oder Stundensatz aus der Nachricht nicht erkennbar
   sind, fragt das UI nach. Sonst wird übersprungen.
4. Das Backend stempelt die strukturierten Daten an den konfigurierten
   Koordinaten auf das aktuelle Template-PDF.
5. Du erhältst das fertige PDF zur Ansicht plus die Buchungs-Übersicht
   als Tabelle.

## Settings-Bereich

Erreichbar über das Zahnrad-Icon oben rechts auf der Hauptseite. Vier Tabs:

### Tab „Allgemein"

- **Anthropic API-Key**: dein persönlicher API-Key von
  [console.anthropic.com](https://console.anthropic.com). Wird nur lokal
  in `settings.json` gespeichert (nicht in Git, nicht in Container-Image).
  Das Auge-Symbol macht den Key sichtbar (Achtung bei Bildschirmaufnahme).
- **Modell**: Auswahl zwischen Sonnet 4.6 (Default, günstig & schnell),
  Opus 4.7 (mächtiger, teurer) und Haiku 4.5 (sehr günstig, weniger
  präzise). Modellwechsel wirkt sofort, kein Neustart nötig.
- **Zuschlagssätze** (Nacht / Sonntag / Feiertag): in Prozent. Werte gehen
  als Default in den Skill ein; Claude darf abweichen, wenn der Nutzer in
  der WhatsApp-Nachricht explizit etwas anderes angibt.
- **API-Key testen**: führt einen Mini-Request gegen Anthropic aus,
  prüft Authentifizierung und Modell-Verfügbarkeit.

### Tab „Skill"

Der **Skill-Prompt** ist die Anweisung, die Claude bei jeder Verarbeitung
als System-Prompt erhält. Er enthält die komplette Geschäftslogik:
Parsing-Regeln, Zuschlagsberechnung, Output-Format.

- **Editor**: voller Markdown-Inhalt mit Monospace-Schrift.
- **Diff anzeigen**: zeigt zeilenweise Unterschiede zur Original-Version
  (was du im Vergleich zur Auslieferung geändert hast).
- **Auf Original zurücksetzen**: stellt die ausgelieferte Version wieder
  her. Deine Änderungen gehen dabei verloren — vorher ggf. den
  Editor-Inhalt rauskopieren.
- **Skill speichern**: schreibt nach `skill.md`. Wirkt ab dem nächsten
  Process-Call sofort.

⚠️ Vorsicht: kaputte Skills bringen den Service nicht zum Absturz, können
aber das Verhalten unbeabsichtigt ändern. Bei Problemen → „Auf Original
zurücksetzen".

### Tab „PDF-Vorlage"

Die Vorlage besteht aus zwei Teilen: dem **PDF** (visuelles Layout) und
einer **Positions-Konfiguration** (`positions.json`, wo welcher Wert
hingestempelt wird).

- **Upload-Zone**: zieh ein neues PDF rein oder klick „Datei wählen".
  Beim Upload wird automatisch Claude Vision benutzt, um die
  Feld-Koordinaten zu erkennen.
- **Aktuelle Vorlage**: Live-Vorschau mit Beispieldaten — so siehst du
  sofort, ob die Positionen sitzen.
- **Positionen als JSON (Fallback-Editor)**: falls Claude Vision die
  Koordinaten leicht daneben legt, kannst du sie hier manuell anpassen.
- **Default wiederherstellen**: setzt Template + Positionen auf die
  ausgelieferte Default-Version zurück.

**Welche Felder erwartet das Template?**

| Feld | Beschreibung |
|---|---|
| `kunde`, `objekt`, `projekt`, `best_nr`, `datum` | Einzeilige Felder im Kopfbereich |
| Tabelle (8 Zeilen) | 3 Spalten: Aufgaben (2-zeilig), Einheiten, Summe |
| `gesamt` | Summe aller Stunden, rechts unten in der Tabelle |
| `bemerkung` | 2-zeiliger Freitext unter der Tabelle |

## Datenpersistenz

Alle benutzergenerierten Daten liegen im konfigurierten `DATA_DIR`
(Standard: `/data`):

```
data/
├── pdfs/                    erzeugte Protokolle, dauerhaft
├── settings.json            API-Key, Modell, Zuschläge
├── skill.md                 aktuell aktiver Skill-Prompt
├── skill.original.md        Original-Backup für Reset/Diff
├── template.pdf             aktuelle PDF-Vorlage
├── positions.json           Feld-Koordinaten der aktuellen Vorlage
└── customers.json           Kunden-Memory (Name + Stundensatz)
```

Beim ersten Container-Start werden alle fehlenden Dateien aus den
Image-Defaults befüllt. Bei einem Container-Update bleiben deine
Editierungen erhalten — nur neue Dateien werden ergänzt.

## Deployment

### Variante 1: native (Python)

Für Entwicklung oder einen Single-Host ohne Docker.

**Voraussetzungen**: Python 3.12+, `poppler-utils` (für PDF-Rendering bei
Template-Uploads).

```bash
# Dependencies
sudo apt install poppler-utils fonts-dejavu-core
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Data-Dir festlegen
export DATA_DIR=/var/lib/abnahme

# Starten
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Service läuft auf `http://localhost:8000`. **Achtung**: in dieser
Variante hat die App keine Authentifizierung — nur in einem privaten
Netz oder hinter einem Reverse-Proxy mit Auth nutzen.

### Variante 2: Docker (einzelner Container)

```bash
# Image bauen
docker build -t abnahme:latest .

# Starten
docker run -d \
  --name abnahme \
  -p 8000:8000 \
  -v /srv/abnahme/data:/data \
  --restart unless-stopped \
  abnahme:latest
```

Service auf `http://host:8000`. Wieder ohne Auth — nur intern nutzen.

### Variante 3: Docker Compose ohne Traefik

Für einen Host ohne bestehenden Reverse-Proxy. Port wird direkt
exponiert.

`docker-compose.simple.yml`:

```yaml
services:
  abnahme:
    build: .
    container_name: abnahme
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /srv/abnahme/data:/data
    environment:
      - TZ=Europe/Berlin
      - LOG_LEVEL=INFO
```

```bash
mkdir -p /srv/abnahme/data
docker compose -f docker-compose.simple.yml up -d
```

### Variante 4: Docker Compose mit Traefik + Authelia

Empfohlene Produktivvariante mit HTTPS und Authentifizierung. Setzt
voraus, dass Traefik und Authelia bereits laufen (Authelia als
ForwardAuth-Middleware unter `middlewares-authelia@file` registriert).

Siehe `docker-compose.yml` im Repo — dort sind die Labels passend
konfiguriert.

```bash
# Image bauen + (optional) in eine Registry pushen
docker build -t ghcr.io/<dein-user>/abnahme:latest .
docker push ghcr.io/<dein-user>/abnahme:latest

# Host vorbereiten
sudo mkdir -p /volume1/docker/abnahme/data/pdfs
sudo chown -R 1026:100 /volume1/docker/abnahme

# Stack hochziehen
docker compose up -d
```

Anpassen in `docker-compose.yml`:

- `image:` → dein Registry-Pfad
- `traefik.http.routers.abnahme.rule` → deine Domain
- `traefik.http.routers.abnahme.tls.certresolver` → dein
  Cert-Resolver-Name
- `traefik.http.routers.abnahme.middlewares` → deine Authelia-Middleware
- `volumes:` → dein Host-Pfad

## Erste Schritte nach dem Deploy

1. Im Browser zur konfigurierten Domain bzw. `http://host:8000`.
2. Über das Zahnrad in **Einstellungen** → Tab **Allgemein**.
3. **Anthropic API-Key** einfügen, **Speichern**, dann **API-Key testen**.
4. (Optional) Modell oder Zuschlagssätze anpassen.
5. (Optional) Tab **PDF-Vorlage**: eigene Vorlage hochladen, Vorschau
   prüfen, ggf. JSON-Positionen anpassen.
6. (Optional) Tab **Skill**: Geschäftslogik anpassen, wenn nötig.
7. Zurück zur Hauptseite, erste WhatsApp-Nachricht einfügen, los.

## Updates

- **Code-Update**: neues Image bauen + pushen, `docker compose pull && docker compose up -d`.
  Editierter Skill, Template, Positionen und Settings bleiben erhalten.
- **Skill-Update**: direkt im UI, kein Neustart nötig.
- **Template-Update**: direkt im UI, kein Neustart nötig.

## Troubleshooting

| Symptom | Ursache / Lösung |
|---|---|
| „API-Key fehlt" | In Settings → Allgemein eintragen und speichern. |
| „API-Key abgelehnt" beim Testen | Key falsch oder Limit erreicht. Auf console.anthropic.com prüfen. |
| Felder im PDF an falscher Stelle | Tab PDF-Vorlage → Positionen-JSON manuell justieren oder neu hochladen. |
| Service reagiert auf nichts | Container-Logs prüfen (`docker logs abnahme`). Bootstrap-Fehler sind dort sichtbar. |
| Skill verhält sich seltsam | Tab Skill → Diff prüfen, ggf. „Auf Original zurücksetzen". |
| PDF-Vorschau leer | Auf Browser umstellen (Firefox/Chrome). Manche WebViews rendern PDFs nicht. Alternativ direkt das PDF aus `/data/pdfs/` ziehen. |
| Vision-Analyse schlägt fehl | Template muss ein normales PDF sein (kein gescanntes Bild). Andernfalls Positionen manuell setzen. |

Container-Logs auslesen:

```bash
docker logs -f abnahme
```

## Kosten

- **Verarbeitung pro Protokoll**: ~2–5 Cent (Sonnet 4.6), ~10–20 Cent
  (Opus 4.7), ~1 Cent (Haiku 4.5).
- **Template-Analyse pro Upload**: ~5–15 Cent (Vision-Call, einmalig pro
  Vorlage).
- **Bei ~10 Protokollen/Woche**: unter 5 €/Monat mit Sonnet.

Hartes Limit auf [console.anthropic.com](https://console.anthropic.com)
unter Settings → Limits setzen.

## API-Referenz

Alle Endpoints unter `/api/`:

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/healthz` | Liveness-Check |
| `GET` | `/api/customers` | Bekannte Kunden + letzte Stundensätze |
| `POST` | `/api/process` | Hauptpipeline: Text → PDF |
| `GET` | `/api/pdf/{name}` | Generiertes PDF abrufen |
| `GET` | `/api/settings` | Settings lesen (Key bleibt maskiert in UI) |
| `POST` | `/api/settings` | Settings patchen |
| `POST` | `/api/settings/test` | API-Key-Probe |
| `GET` | `/api/skill` | Aktueller Skill + Original (für Diff) |
| `POST` | `/api/skill` | Skill speichern |
| `POST` | `/api/skill/reset` | Skill auf Original zurücksetzen |
| `GET` | `/api/template` | Metadaten der aktuellen Vorlage |
| `GET` | `/api/template/pdf` | Aktuelles Template-PDF |
| `GET` | `/api/template/preview` | Vorschau mit Beispiel-Daten (PDF) |
| `GET` | `/api/template/preview.png` | Vorschau als PNG |
| `POST` | `/api/template/upload` | Neue Vorlage hochladen (+ Vision-Analyse) |
| `POST` | `/api/template/positions` | Positions-JSON überschreiben |
| `POST` | `/api/template/reset` | Auf Default-Vorlage zurücksetzen |
