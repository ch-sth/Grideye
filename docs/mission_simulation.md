# Dashboard und Missionssimulation

Die Beschreibung der Vorab-Simulation ist in die bestehende FastAPI-/MQTT-/PostgreSQL-
Architektur integriert. Die Anwendung läuft ausschließlich im **SIMULATION-Modus**.
Sie sendet keine Motorbefehle und ersetzt keine Failsafes eines realen Flight Controllers.

## Bedienung

1. `./start.sh` starten und `http://localhost:8000/` öffnen. Die bisherige Weiterleitung
   auf `/?ansicht=neu` bleibt erhalten. Bei älterer Browseransicht einmal Strg+F5 drücken.
2. **Pfad festlegen** wählen und Startposition auf der Karte anklicken.
3. Wegpunkte im Grid anklicken. Zwischen Frei, Zellmitte, Rasterpunkt und Automatisch wählen.
4. **Endpunkt festlegen** wählen und die Landeplattform anklicken.
5. Name, Flughöhe, Geschwindigkeit und Hover-Zeit einstellen. Koordinaten können auch
   in der Punktliste bearbeitet werden; das Backend prüft die Grenzen beim Speichern.
6. **Pfad speichern**, anschließend **Mission starten**. Start und Ende werden nicht gesnappt.
7. Pause hält die Position und den Hover-Timer an. Fortsetzen setzt die Mission fort.
   Abbrechen leitet eine simulierte Landung ein und erhält den gespeicherten Pfad.
8. Nach der Landung kann dieselbe Mission erneut gestartet werden. Reset erhält den Pfad.
   Nur **Pfad löschen** entfernt die Route. Missionsmetadaten bleiben erhalten,
   damit bestehende Datenbankfunde ihre Missionsreferenzen behalten.

Die Drohne hebt an ihrer aktuellen Position ab und fliegt zuerst zur Startposition,
anschließend zu allen Wegpunkten und zum Ende. Es gibt keine Teleportation zum Start.
Die Hover-Zeit gilt nur für normale Wegpunkte. Nach einer manuellen Höhenänderung
stellt Fortsetzen zunächst die geplante Höhe wieder her.

## Karte und vorhandene Funde

Das voreingestellte Grid umfasst 2 × 2 m mit 20-cm-Zellen (A1–J10). Die erlaubte
Flugzone liegt 25 cm außerhalb des Grids. Ihre Ecken sind die vier simulierten Anker.
Andere Gridgrößen und der Abstand lassen sich über die Service-Einstellungen konfigurieren.
Grid, Abstand und Ankerzuordnung können nur geändert werden, wenn keine Mission aktiv
und die Drohne am Boden ist. Gespeicherte Pfade werden vor jedem Start erneut geprüft.

Bestehende Erkennungen bleiben unverändert gespeichert. Die Karte und der Zellfilter
ordnen sie anhand ihrer Weltkoordinaten dem aktuellen Grid zu. Die Tabelle zeigt auch
abweichende ursprüngliche Zellnamen an. Funde außerhalb des neuen Grids bleiben in
Tabelle und Datenbank sichtbar, werden aber nicht als Zelle auf der Karte eingezeichnet.

Die Karte bleibt auf Desktop-Bildschirmen vollständig sichtbar. Das rechte Bedienpanel
scrollt unabhängig. Auf kleinen Displays werden Karte und Bedienelemente untereinander angezeigt.

## Prioritäten und Failsafe

`FAILSAFE > RADIO > USB GAMEPAD > AUTO` gilt zentral im Backend. Funk- oder USB-
Übernahme pausiert die Mission. Nach Freigabe muss ausdrücklich **Fortsetzen** gewählt werden.
USB-Eingaben werden während der Funkübernahme ignoriert.

Im Testpanel werden Funk und USB simuliert. L1+R1 übernimmt, L2+R2 gibt frei,
Kreis landet. Richtungstasten gedrückt halten; beim Loslassen werden die Achsen null.
Der Browser sendet dabei die Eingaben für einen simulierten Controller. Reißt dieser
Eingabestrom während der Handsteuerung ab, landet die Simulation. Es wird keine
Browser-Gamepad-API zur Anbindung eines echten Pi-USB-Controllers verwendet.

Die zentrale Überwachung prüft Flugzonengrenzen, Ankerzahl, Qualität, UWB-Datenalter,
Flight-Controller-Verbindung und den aktiven Gamepad-Eingabestrom. Standardmäßig lösen
mehrere fehlerhafte Messungen den Failsafe aus. Automatische horizontale Bewegung endet,
die Mission wird abgebrochen und die simulierte Höhe kontrolliert auf null reduziert.

Failsafe bleibt nach der Landung verriegelt. **Sensoren wiederherstellen** stellt im
Test die Verbindungen her und setzt die simulierte Position zurück ins Grid.
Anschließend **Reset** wählen. Ein Reset bei aktiver Ursache oder in der Luft wird abgelehnt.
Die Prüfungen laufen auch bei Funkübernahme, USB-Steuerung und pausierten Missionen.
Automatische Missionen laufen weiter, wenn die Browser-Verbindung unterbrochen wird.

## UWB, Hardware und Erweiterungsgrenzen

Unter **UWB / Position** können Einzelbetrieb und Master/Slave sowie vier eindeutige
simulierte Gerätezuordnungen gespeichert werden. Nicht zugeordnete Slots zählen nicht
als gültige Anker. Geräteverbindungen können im Testpanel gezielt unterbrochen werden.
**USB-Geräte suchen** listet zusätzlich sichtbare serielle Geräte anhand von by-id-Namen
oder ttyACM/ttyUSB auf. Diese Einträge sind unbestätigtes Inventar, keine verbundenen UWB-Anker.
Im Docker-Container sind die USB-Geräte des Hosts nicht automatisch verfügbar.

Die Provider-Grenzen in `services/mission/providers.py` halten Missionslogik und
konkrete Geräte getrennt. Reale UWB-Protokolle, Linux-Gamepad-Erfassung und MAVLink
sind noch nicht implementiert. REAL HARDWARE ist deshalb noch nicht auswählbar.
Kamera/OCR bleiben die bisherigen Erweiterungspunkte. Anker-Distanzen, UWB-Fehler,
Positionsunsicherheiten und echte Höhen-Sensorfusion benötigen entsprechende Gerätedaten.

## Backend und Datenhaltung

- Missionen: `POST/GET /api/v1/missions`, `GET/PUT /api/v1/missions/{id}`.
- Aktionen: `POST /api/v1/missions/{id}/start|pause|resume|abort`.
- Route löschen: `DELETE /api/v1/missions/{id}`.
- Snap-Prüfung: `POST /api/v1/missions/snap`.
- Simulation: `GET /api/v1/simulation`, `POST /api/v1/simulation/input|land|reset`.
- Geräteinventar: `GET /api/v1/uwb/devices`.
- Live-Snapshot: WebSocket `/ws/live`, Ereignistyp `simulation.telemetry`.
- Einstellungen: `PUT /api/v1/config/safety|anchors|grid`.

Vollständige Pläne stehen in der zusätzlichen Tabelle `mission_plans`; vorhandene
Missions- und Fundtabellen werden nicht umgeschrieben. Für Alembic gibt es Revision 0002.
Die Bootstrap-Schemaerstellung legt die zusätzliche Tabelle auch bei bestehenden
Installationen an. Nach einem Backend-Neustart bleiben Pläne erhalten; zuvor laufende
Missionen erhalten den Status `interrupted` und starten nicht automatisch neu.

Die Physik-/Sicherheitsprüfung läuft unabhängig von WebSocket-Auslieferung und
Datenbankzugriffen. Der Stack verwendet genau einen Backend-Prozess mit einem
Missionsmanager; mehrere Worker/Backend-Replikate sind für diesen Modus nicht vorgesehen.

Die früheren unabhängigen UWB- und Flight-Simulator-Container befinden sich im Compose-
Profil `legacy-simulation`. Im Standardbetrieb liefert die zentrale Simulation Positions-
und Flugtelemetrie auch auf den vorhandenen MQTT-Topics. Das Legacy-Profil nicht zusammen
mit der Missionssimulation verwenden: konkurrierende Simulatoren erzeugen widersprüchliche Daten.
