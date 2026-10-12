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
    echo "Fehler: .env fehlt. Stelle die beim Start verwendete .env wieder her." >&2
    exit 1
fi

docker compose --env-file .env -f compose.yaml down
echo "Grideye wurde gestoppt. Gespeicherte Daten bleiben erhalten."
