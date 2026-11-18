# Grideye

Grideye is an ARM64-friendly, modular bootstrap for indoor grid inspection. It deliberately uses
simulators and typed adapter boundaries. The backend provides mission execution and failsafe
behavior **in simulation only**. Real motor control and flight failsafes remain the flight
controller's responsibility.

## Windows quick start mit Docker Desktop

Diese Anleitung ist fuer Windows gedacht. Das Projekt laeuft dabei komplett in Docker-Containern,
deshalb musst du Python oder die einzelnen Services nicht lokal starten.

### 1. Docker Desktop installieren

1. Lade Docker Desktop fuer Windows herunter: <https://www.docker.com/products/docker-desktop/>
2. Installiere Docker Desktop mit den Standardoptionen.
3. Aktiviere WSL 2, falls Docker Desktop danach fragt.
4. Starte den Computer neu, falls die Installation das verlangt.
5. Oeffne Docker Desktop und warte, bis unten links `Engine running` oder ein aehnlicher
   gruener Status angezeigt wird.

Wenn Docker Desktop nicht startet, pruefe in Windows, ob Virtualisierung aktiviert ist und ob WSL
installiert ist. Docker Desktop fuehrt dich normalerweise durch diese Schritte.

### 2. Projekt vorbereiten

Oeffne PowerShell im Projektordner, also in diesem Verzeichnis:

```powershell
cd D:\Schule\Projektarbeit\Software\grideye\Grideye
```

Lege danach die lokale Umgebungsdatei an:

```powershell
Copy-Item .env.example .env
```

Optional kannst du die Datei `.env` oeffnen und das Datenbankpasswort anpassen. Fuer einen lokalen
Teststart reicht die Beispieldatei normalerweise aus.

### 3. Projekt starten

Starte alle Container mit Docker Compose:

```powershell
docker compose --env-file .env -f compose.yaml up -d --build
```

Der erste Start kann ein paar Minuten dauern, weil Docker die Images baut. Danach ist das Dashboard
im Browser erreichbar:

```text
http://localhost:8000/
```

Die API-Dokumentation findest du hier:

```text
http://localhost:8000/docs
```

### 4. Pruefen, ob alles laeuft

Zeige die laufenden Container an:

```powershell
docker compose --env-file .env -f compose.yaml ps
```

Logs anzeigen:

```powershell
docker compose --env-file .env -f compose.yaml logs -f
```

### 5. Projekt stoppen

Stoppe die Container mit:

```powershell
docker compose --env-file .env -f compose.yaml down
```

Die gespeicherten Daten bleiben dabei in Docker-Volumes erhalten.

Hinweis: Die Dateien `start.sh` und `stop.sh` sind Bash-Skripte. Unter Windows funktionieren sie
direkt nur mit Git Bash oder WSL. In PowerShell verwende stattdessen die Docker-Compose-Befehle aus
dieser Anleitung.

## Quick start on Raspberry Pi OS 64-bit

Prerequisites are Git, Docker Engine with Compose v2, and (for host development) Python 3.12+
plus [uv](https://docs.astral.sh/uv/). Docker images used here publish ARM64 variants.

```bash
cp .env.example .env             # replace the example database password
docker compose --env-file .env build
docker compose --env-file .env up -d
curl http://localhost:8000/api/v1/system/health
open http://localhost:8000/docs  # or use a browser on another machine
```

The dashboard is at `http://localhost:8000/`. Run `make ps`, `make logs`, `make smoke`, and
`make down` for common operations. Host-side setup and tests use `make setup`, `make test`, and
`make lint`. Integration tests require the running stack: `make integration`.

Alternatively, use the executable scripts in the project root:

```bash
./start.sh  # build the current code and start all services in the background
./stop.sh   # stop and remove containers; preserve database and MQTT data volumes
```

Both scripts require Docker Compose v2 and a configured `.env` file. They also work
when called by absolute path from another directory. After code changes, run
`./start.sh` again to rebuild and update the services. The dashboard may take a
short time to become available after startup.

On small Pis, the first multi-service build may be memory-heavy because each service references
the same build context; Compose/Docker layer caching avoids rebuilding identical layers. No AI
weights are downloaded.

## Architecture

```mermaid
flowchart LR
  S[Backend mission simulation] -->|position and telemetry| M[(Mosquitto)]
  S --> C[Control priorities and simulation safety]
  G[Future AI + grid mapping] -->|grid/detection| M
  M --> T[Tracking]
  T -->|detection/confirmed| M
  M --> B[FastAPI backend]
  B <--> P[(PostgreSQL)]
  B -->|REST + WebSocket| D[Static dashboard]
  FC[Flight controller failsafes] -. future adapter .-> S
```

## API and persistence

OpenAPI is available at `/docs`. The API includes health/services, current position and
telemetry, mission CRUD/state actions, detections, grid cells and configuration reads. The
configuration API validates and atomically persists settings with `PUT /api/v1/config/{name}`.

The dashboard offers an interactive grid, persisted detections and service pages at
`/services/{service}`. Missing heartbeats are unknown; stale heartbeats are offline.
MQTT and database connections are checked from the backend and do not prove hardware connectivity.
Compose mounts the host `config` directory so settings survive container replacement.
Grid, safety, anchor mappings and the heartbeat timeout update immediately. Grid, safety and
anchor changes require an idle, landed simulation. Logging and tracking proximity require
a restart. The old UWB settings apply only to the optional legacy simulator. IP-camera preview and AI inference run in the backend.
Grid-mapping remains a future adapter. Mission, UWB and flight simulation run in the backend.
Credentials remain in `.env` / Compose.
Settings edits are shared by dashboard users; the last save wins.
Only missions, confirmed detections and system events are modeled for persistence; high-rate
telemetry stays in memory.

## Mission planning and simulation

The dashboard provides a 2 × 2 m field (A1–J10), a 25 cm flight-zone margin,
graphical routes with four snap modes, persistent mission plans, hover timers and
repeatable flights. Radio and USB takeovers, anchor failures and communication losses
can be tested in the browser. The backend owns priorities, simulation safety and execution.
Real UWB, USB gamepad and MAVLink providers are not implemented yet.
See [the simulation guide](docs/mission_simulation.md) for operation, API and adapter limits.

## MQTT topics

| Area | Topics |
|---|---|
| UWB | `grideye/uwb/position`, `grideye/uwb/status` |
| Flight | `grideye/flight/telemetry`, `attitude`, `battery`, `mode`, `status`, `command`, `command/result` |
| Mission | `grideye/mission/command`, `status`, `progress`, `current_target` |
| Vision | `grideye/camera/status`, `grideye/ai/status`, `grideye/ai/detection`, `grideye/grid/detection` |
| Results | `grideye/detection/confirmed` |
| System | `grideye/system/services/{service}/status`, `grideye/system/events` |

All actual constants live centrally in `grideye_shared.mqtt`. QoS/retain rationale is documented
in [docs/mqtt.md](docs/mqtt.md).

## Hardware extension points

- Implement `UwbProvider` in `services/uwb` for the selected UWB hardware.
- Implement `FlightAdapter` in `services/flight` to encapsulate MAVLink. Never auto-arm or bypass
  flight-controller safeguards.
- IP-camera capture and live preview are implemented in `services/camera/live.py`.
  Stream settings belong in `config/camera.yaml`. Images remain outside MQTT.
- `services.ai.detectors.ArucoDetector` replaces OCR. Call `await detector.detect(frame)`
  with encoded PNG/JPEG bytes. Default dictionary: `DICT_4X4_1000` (IDs 0-999).
  Pass a different OpenCV dictionary name to the constructor if required. Printed tags
  must use the same dictionary and have a white margin.
  Results use class `aruco`, the tag ID in `number`, pixel bounding boxes and actual
  frame dimensions. `marker_confidence` replaces `ocr_confidence`; external MQTT
  producers must update this field. Confidence 1.0 means successfully decoded,
  not a calibrated probability. No model weights are required.
  See the [OpenCV ArUco API](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html).
  The backend applies the active detector to live camera frames and publishes results
  on `grideye/ai/detection`. The legacy AI main process is only a standalone heartbeat.

The current nadir projection only supports roll/pitch zero and a simplified pinhole camera. Full
extrinsics, homography and distortion handling are explicit follow-up work.

## IP-Kamera im Dashboard

1. Im Reiter **Kamera** unter **Einstellungen** das Feld **Kamera-IP oder Stream-URL** ausfüllen.
   Beispiele: `192.168.1.50`, `rtsp://192.168.1.50:554/stream1`,
   `rtsp://benutzer:passwort@192.168.1.50:554/stream1` oder
   `http://192.168.1.50:8080/video` (HTTP-MJPEG).
2. **Einstellungen speichern**: Die Kamera wird sofort verbunden, ohne Neustart.
   Das Livebild erscheint über den Einstellungen. Zum Wechseln eine andere Adresse speichern.
3. Zum Trennen das Adressfeld leeren und speichern. Die Auswahl bleibt über Neustarts erhalten.

Eine reine IP wird zu `rtsp://IP` ergänzt. Stream-Pfad, Port und gegebenenfalls Zugangsdaten
müssen zum Kameramodell passen; eine Kamera-Weboberfläche ist kein Video-Stream.
Das Backend bzw. dessen Docker-Container muss die Kamera im Netzwerk erreichen können.
Zugangsdaten in URLs werden in der gemeinsamen Kamerakonfiguration gespeichert.
Die Kamera-Einstellungen gelten für alle Dashboard-Nutzer.

Das Backend verwendet eine gemeinsame OpenCV/FFmpeg-Verbindung mit Lese- und
Verbindungszeitlimit und versucht nach Fehlern erneut zu verbinden. Der Browser lädt
aktuelle JPEG-Vorschaubilder mit bis zu fünf Bildern pro Sekunde; veraltete Bilder werden
ausgeblendet. `GET /api/v1/camera/status` liefert den Verbindungsstatus,
`GET /api/v1/camera/frame.jpg` das aktuelle Bild oder HTTP 503.
Die [OpenCV-Zeitlimits](https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html)
begrenzen blockierende Netzwerkzugriffe. GStreamer-Pipelines werden weiterhin nicht ausgeführt.
Nach einem Kameratausch die Kalibrierung für Projektion und Grid-Zuordnung anpassen.
Der aktive Detektor (ArUco oder YOLO) wertet den Livefeed im Backend aus.

## YOLO-Modell importieren und aktivieren

Im Dashboard unter **KI-Modelle** lassen sich Ultralytics-kompatible YOLO-Modelle für
Objekterkennung (`detect`, `.pt`) importieren. Andere PyTorch-Architekturen, reine
`state_dict`-Dateien und Klassifikations-/Segmentierungsmodelle werden nicht unterstützt.
Die Einbindung verwendet die [Ultralytics-Python-API](https://docs.ultralytics.com/usage/python/).

- **Über Serverpfad:** Die `.pt`-Datei im Projektordner `model-imports` ablegen.
  Im Dialog beispielsweise `/model-imports/best.pt` eingeben und **Importieren & aktivieren**
  wählen. Docker stellt diesen Ordner schreibgeschützt im Backend bereit. Bei einem
  Betrieb ohne Docker kann ein lesbarer lokaler Serverpfad verwendet werden.
- **Vom PC:** Über die Dateiauswahl eine `.pt`-Datei auswählen und **Hochladen & aktivieren**
  wählen. Das funktioniert auch, wenn der Browser auf einem anderen Rechner läuft;
  ein Windows-Dateipfad kann nicht als Serverpfad im Linux-Container verwendet werden.
- **Wechseln:** Bei einem bereits importierten Modell **Aktivieren** wählen.
  **ArUco** ist ebenfalls auswählbar und benötigt keine Modelldatei.

Das Programm kopiert jede Datei (maximal 512 MiB), erfasst ihre SHA-256-Prüfsumme und
prüft das Modell mit einer echten Testauswertung, bevor es die aktive Auswahl umschaltet.
Importfehler lassen das bisherige Modell aktiv. Die Originaldatei bleibt erhalten.
Modelle und Auswahl werden unter `models/` gespeichert; in Docker liegt dieser Ordner im
Volume `ai_models` und bleibt beim normalen Stoppen/Neustarten erhalten. `docker compose down -v`
löscht auch dieses Volume. Die Auswahl gilt für alle Dashboard-Nutzer. Verwende eigene oder
vertrauenswürdige `.pt`-Dateien, da PyTorch-Checkpoints Python-Objekte enthalten können.

Die CPU-Version von PyTorch wird über den
[offiziellen CPU-Paketindex](https://docs.astral.sh/uv/guides/integration/pytorch/) installiert.
Der erste Build ist deshalb größer und dauert länger. Nach dem Update einmal `./start.sh`
ausführen; anschließend sind Modellwechsel ohne Neustart möglich.

Die Liveauswertung arbeitet unabhängig vom Kamera-Preview mit maximal zwei Auswertungen
pro Sekunde (bei langsamen Modellen entsprechend weniger). Sie verwendet YOLO mit 640 Pixeln
Eingangsgröße und einer Konfidenzschwelle von 0,25. Ergebnisse erscheinen unter **KI-Modelle**
und werden auf `grideye/ai/detection` veröffentlicht. Die automatische Grid-Projektion ist
weiterhin nicht angeschlossen; es werden keine ungeprüften Weltkoordinaten gespeichert.

API: `GET /api/v1/ai/models`, `POST /api/v1/ai/models/import` mit `{"path":"..."}`,
`POST /api/v1/ai/models/upload?filename=best.pt` mit binärem Dateiinhalt,
`POST /api/v1/ai/models/activate` mit `{"model_id":"..."}` (oder `aruco`) und
`GET /api/v1/ai/result`. Der Backend-Prozess wird mit einem Worker betrieben, damit die
Modellauswahl und der Kamerazugriff gemeinsam verwaltet werden.
