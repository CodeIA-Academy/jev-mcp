#!/usr/bin/env bash
# Prueba de humo del MCP de Jev: handshake + tools/list + una llamada real.
# Sin TYPESAFE_API_KEY la última debería devolver un error de autenticación claro
# (eso ya demuestra que el transporte, el esquema y el camino HTTP funcionan).
#
# Uso:  TYPESAFE_API_KEY=sk-... bash smoke_test.sh
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"

{
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ask_jev","arguments":{"state":"Llevo tres días sin poder cobrar y estoy perdiendo ventas, esto es urgente.","questions":{"urgencia":{"type":"noul","instructions":"¿Este mensaje expresa urgencia?"},"equipo":{"type":"choice","instructions":"¿Qué equipo debería atenderlo?","criteria":{"facturacion":"Pagos, facturas y devoluciones","tecnico":"Errores, caídas e integraciones","ventas":"Precios y cuentas nuevas"}},"enfado":{"type":"score","instructions":"Cuánto enfado muestra el cliente","criteria":["Tranquilo, solo expone hechos","Molesto pero educado","Muy enfadado, lenguaje fuerte"]}}}}}'
  sleep 20
} | "$PY" "$DIR/server.py" 2>/tmp/jev_mcp_stderr.log

echo
echo "--- stderr del servidor ---"
cat /tmp/jev_mcp_stderr.log
