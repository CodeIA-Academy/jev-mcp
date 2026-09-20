#!/usr/bin/env bash
# Lanzador del MCP de Jev: carga la clave desde jev-mcp/.env (si existe) y arranca el servidor.
# Así la clave vive en UN solo fichero y las configuraciones solo apuntan a este script.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$DIR/.env"
  set +a
fi
PY="${TYPESAFE_PYTHON:-python3}"
exec "$PY" "$DIR/server.py"
