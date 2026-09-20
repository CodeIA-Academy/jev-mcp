#!/usr/bin/env bash
# Demo del proyecto de la lección: el clasificador que decide.
# Entra un enlace o un mensaje y hay que decidir si es recurso, blog o clase,
# con una prioridad compuesta por tres Scores y un guardrail de confianza.
# La clave se lee de jev-mcp/.env a través de run.sh.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$DIR" <<'PY'
import json, subprocess, sys, os

DIR = sys.argv[1]

def ask(state, questions):
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo", "version": "1.0"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "ask_jev", "arguments": {"state": state, "questions": questions}}},
    ]
    entrada = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs)
    p = subprocess.run(["bash", os.path.join(DIR, "run.sh")], input=entrada,
                       capture_output=True, text=True, timeout=120)
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("id") == 2:
            return m["result"].get("structuredContent", {})
    return {"error": p.stderr[-400:]}

ENLACES = [
    "https://github.com/browser-use/browser-harness - Conecta un LLM a tu Chrome real y el agente "
    "escribe sus propios helpers cuando le falta uno. Python, MIT, 17.700 estrellas.",
    "https://x.com/claudedevs/status/2092672740197081360 - Anthropic ha añadido una Admin API a sus "
    "SDKs y a su CLI ant: gestionar miembros, workspaces y claves por código.",
    "https://github.com/mutonby/vibetube - Grabador multicámara para macOS que pasa la carpeta a un "
    "agente que monta el vídeo. Solo macOS y no es gratis.",
]

PREGUNTAS = {
    "tipo": {"type": "choice",
             "instructions": "¿Qué debería ser este material en el vault de Codeia?",
             "criteria": {
                 "recurso": "Una herramienta, repositorio, web o servicio para el directorio de recursos.",
                 "blog": "Un tema para escribir un artículo o un post: noticia, tendencia o análisis.",
                 "clase": "Material docente para estudiar o reproducir en directo en una clase.",
             }},
    "valor": {"type": "score",
              "instructions": "Cuánto valor aporta a nuestra audiencia (devs que usan agentes e IA aplicada)",
              "criteria": ["Poco o redundante", "Útil pero común", "Aporta de verdad, lo usaríamos"]},
    "verificable": {"type": "score",
                    "instructions": "Cuánta fuente sólida y comprobable hay detrás",
                    "criteria": ["Solo un tuit o una promesa", "Documentación o repo público", "Datos reproducibles y fechas"]},
    "esfuerzo": {"type": "score",
                 "instructions": "Cuánto trabajo cuesta sacarle una pieza publicable",
                 "criteria": ["Se publica casi tal cual", "Hay que probar y escribir", "Hay que montarlo y medirlo"]},
}

for i, enlace in enumerate(ENLACES, 1):
    print(f"\n==================== ENLACE {i} ====================")
    print(enlace[:110] + ("…" if len(enlace) > 110 else ""))
    datos = ask(enlace, PREGUNTAS)
    if "error" in datos:
        print("ERROR:", datos["error"])
        continue
    a = datos.get("answers", {})
    tipo = a.get("tipo", {})
    print(f"  tipo: {tipo.get('choice')}  (confianza {tipo.get('confidence')}, {json.dumps(tipo.get('probabilities'), ensure_ascii=False)})")
    for clave in ("valor", "verificable", "esfuerzo"):
        d = a.get(clave, {})
        print(f"  {clave}: {d.get('score')}  (confianza {d.get('confidence')})")
    conf = tipo.get("confidence", 0)
    print(f"  → guardrail: {'AUTOMÁTICO' if conf >= 0.8 else 'A REVISIÓN HUMANA'}")
    print(f"  → tokens: {datos.get('usage')}")
PY
