#!/usr/bin/env bash
# Prueba real contra la API de TypeSafe a traves del MCP: tres primitivas en una llamada,
# y comparacion español/ingles con el mismo contenido.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"

call() {  # call <etiqueta> <json-de-la-pregunta>
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"prueba","version":"1.0"}}}' \
    "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" \
    | bash "$DIR/run.sh" 2>/dev/null \
    | python3 -c '
import json,sys
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try: m=json.loads(line)
    except Exception: continue
    if m.get("id")==2:
        r=m.get("result",{})
        print(r.get("content",[{}])[0].get("text","(sin texto)"))
        print("---structuredContent---")
        print(json.dumps(r.get("structuredContent"), ensure_ascii=False))
'
}

echo "################ 1) LISTAR MODELOS ################"
call list_jev_models '{}'

echo
echo "################ 2) TICKET EN ESPAÑOL (choice + score + noul) ################"
call ask_jev '{"state":"Llevo tres días sin poder cobrar y el soporte no me contesta. Estoy perdiendo ventas y no sé qué hacer. Esto es urgente.","questions":{"equipo":{"type":"choice","instructions":"¿Qué equipo debería atender esto?","criteria":{"facturacion":"Pagos, suscripciones y devoluciones","tecnico":"Errores, caídas e integraciones","ventas":"Precios y cuentas nuevas"}},"enfado":{"type":"score","instructions":"Cuánto enfado muestra el cliente","criteria":["Tranquilo, solo expone hechos","Molesto pero educado","Muy enfadado, lenguaje fuerte"]},"urgencia":{"type":"noul","instructions":"¿El mensaje expresa urgencia o prisa?"}}}'

echo
echo "################ 3) EL MISMO TICKET EN INGLÉS (para medir el idioma) ################"
call ask_jev '{"state":"I have been unable to get paid for three days and support is not answering. I am losing sales and do not know what to do. This is urgent.","questions":{"equipo":{"type":"choice","instructions":"Which team should handle this?","criteria":{"facturacion":"Payments, subscriptions and refunds","tecnico":"Bugs, outages and integrations","ventas":"Pricing and new accounts"}},"enfado":{"type":"score","instructions":"How frustrated does the customer appear","criteria":["Calm, just stating facts","Frustrated but civil","Very angry, strong language"]},"urgencia":{"type":"noul","instructions":"Does the message convey urgency or time-sensitivity"}}}'
