#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if ! command -v docker >/dev/null 2>&1; then
    echo "Fehler: Docker ist nicht installiert." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Fehler: Docker Compose v2 ist nicht verfügbar." >&2
    exit 1
fi
if [[ ! -f .env ]]; then
    echo "Fehler: .env fehlt. Kopiere .env.example nach .env und lege das Datenbankpasswort fest." >&2
    exit 1
fi

docker compose --env-file .env -f compose.yaml up -d --build
echo "Grideye wurde gestartet. Dashboard: http://localhost:8000/"
echo "Das Dashboard kann während der Initialisierung noch kurz nicht erreichbar sein."
