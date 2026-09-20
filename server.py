#!/usr/bin/env python3
"""
jev-mcp — servidor MCP (stdio) que expone TypeSafe / Jev como herramienta para agentes.

Jev no escribe texto: evalúa un `state` contra preguntas tipadas (choice / score / noul)
y devuelve valores con su distribución de probabilidad. Este servidor le da a cualquier
agente (Claude Code, Codex, Orca, Hermes...) dos herramientas:

  - ask_jev:          manda estado + preguntas y devuelve las respuestas tipadas
  - list_jev_models:  lista los modelos y alias disponibles en la cuenta

Protocolo: MCP sobre stdio, mensajes JSON-RPC delimitados por salto de línea.
stdout es SOLO JSON-RPC; los avisos van a stderr.

Variables de entorno:
  TYPESAFE_API_KEY       (obligatoria para llamar a la API) — console.typesafe.ai/keys
  TYPESAFE_DEFAULT_MODEL (opcional, por defecto jev-latest)
  TYPESAFE_BASE_URL      (opcional, por defecto https://api.typesafe.ai)
"""

import json
import os
import sys
import urllib.error
import urllib.request

SERVER_NAME = "jev-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-06-18"
BASE_URL = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
DEFAULT_MODEL = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = float(os.environ.get("TYPESAFE_TIMEOUT", "90"))

VALID_TYPES = ("choice", "score", "noul")


def log(msg):
    """Avisos a stderr: stdout está reservado para JSON-RPC."""
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def api_key():
    return os.environ.get("TYPESAFE_API_KEY", "").strip()


def http(method, path, payload=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    key = api_key()
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"raw": raw[:800]}
        return None, {
            "status": e.code,
            "error": detail,
            "hint": {
                401: "Falta la clave o no es válida. TYPESAFE_API_KEY debe estar exportada.",
                403: "La API pide una clave válida (authentication_error). Revisa TYPESAFE_API_KEY.",
                422: "El cuerpo falló la validación: mira el campo que señala el error.",
                429: "Límite de peticiones superado (250k tok/s, 1200 req/min): reintenta con backoff.",
                529: "TypeSafe está sobrecargado: reintenta en unos segundos.",
            }.get(e.code, "Error de la API de TypeSafe."),
        }
    except Exception as e:  # red, DNS, timeout
        return None, {"status": None, "error": {"message": f"{type(e).__name__}: {e}"}, "hint": "No se pudo contactar con api.typesafe.ai."}


def validate_questions(questions):
    """Devuelve (errores, preguntas_normalizadas)."""
    errors = []
    if not isinstance(questions, dict) or not questions:
        return ["`questions` debe ser un objeto con al menos una pregunta."], questions
    for qid, q in questions.items():
        if not isinstance(q, dict):
            errors.append(f"La pregunta `{qid}` debe ser un objeto.")
            continue
        qtype = str(q.get("type", "")).lower()
        if qtype not in VALID_TYPES:
            errors.append(f"La pregunta `{qid}` tiene type='{qtype or '?'}': debe ser choice, score o noul.")
            continue
        q["type"] = qtype
        if not q.get("instructions"):
            errors.append(f"La pregunta `{qid}` no tiene `instructions`.")
        criteria = q.get("criteria")
        if qtype == "choice":
            if not isinstance(criteria, dict) or len(criteria) < 2:
                errors.append(f"Choice `{qid}` necesita `criteria` como objeto con al menos dos opciones.")
            elif not any(v is None or isinstance(v, str) for v in criteria.values()):
                errors.append(f"Choice `{qid}`: cada opción debe describirse con texto o quedar a null.")
        elif qtype == "score":
            if not isinstance(criteria, list) or len(criteria) < 2:
                errors.append(f"Score `{qid}` necesita `criteria` como lista ordenada de al menos dos niveles.")
        elif qtype == "noul":
            if criteria is not None and (
                not isinstance(criteria, dict) or set(criteria) - {"true", "false"}
            ):
                errors.append(f"Noul `{qid}`: `criteria` es opcional y solo admite las claves 'true' y 'false'.")
    return errors, questions


def summarize(model, answers, usage=None):
    """Resumen legible en texto; el JSON crudo va aparte."""
    lines = [f"Jev ({model}) respondió {len(answers)} pregunta(s):"]
    for qid, a in answers.items():
        t = a.get("type")
        if t == "choice":
            lines.append(
                f"  · {qid}: choice = {a.get('choice')} "
                f"(confianza {a.get('confidence')}, probabilidades {json.dumps(a.get('probabilities'), ensure_ascii=False)})"
            )
        elif t == "score":
            lines.append(
                f"  · {qid}: score = {a.get('score')} de {len(a.get('legend') or {})} niveles "
                f"(confianza {a.get('confidence')})"
            )
        elif t == "noul":
            lines.append(f"  · {qid}: noul = {a.get('noul')}")
        else:
            lines.append(f"  · {qid}: {json.dumps(a, ensure_ascii=False)}")
    if usage:
        lines.append(f"  tokens: {usage.get('input_tokens')} entrada / {usage.get('output_tokens')} salida")
    lines.append("")
    lines.append("Cómo leerlo: choice y score traen `confidence` (0-1). Noul no: su probabilidad ES la señal.")
    lines.append("Actúa con confianza alta; pide confirmación con media; escala a una persona con baja.")
    return "\n".join(lines)


def tool_result(text, structured=None, is_error=False):
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def call_ask_jev(args):
    state = args.get("state")
    if state is None:
        return tool_result("Falta `state`: es el contenido a evaluar (texto o JSON).", is_error=True)
    errors, questions = validate_questions(args.get("questions"))
    if errors:
        return tool_result("Revisa las preguntas:\n- " + "\n- ".join(errors), is_error=True)

    model = args.get("model") or DEFAULT_MODEL
    payload = {"state": state, "model": model, "questions": questions}
    data, err = http("POST", "/v1/systemone", payload)
    if err:
        return tool_result(
            f"No se pudo evaluar con Jev (HTTP {err['status']}): {err['hint']}\n"
            f"Detalle: {json.dumps(err['error'], ensure_ascii=False)[:500]}",
            structured={"error": err},
            is_error=True,
        )

    answers = data.get("answers", {})
    usage = data.get("usage")
    text = summarize(data.get("model", model), answers, usage)
    text += "\n\nRespuesta completa (JSON):\n" + json.dumps(data, ensure_ascii=False, indent=2)
    return tool_result(text, structured={"model": data.get("model", model), "answers": answers, "usage": usage})


def call_list_models(_args):
    data, err = http("GET", "/v1/models")
    if err:
        return tool_result(
            f"No se pudo listar los modelos (HTTP {err['status']}): {err['hint']}\n"
            f"Detalle: {json.dumps(err['error'], ensure_ascii=False)[:500]}",
            structured={"error": err},
            is_error=True,
        )
    models = data.get("models", data if isinstance(data, list) else [])
    lines = ["Modelos disponibles en esta cuenta:"]
    for m in models:
        if isinstance(m, dict):
            lines.append(f"  · {m.get('name')} — {m.get('description', '')}".rstrip(" —"))
        else:
            lines.append(f"  · {m}")
    lines.append("")
    lines.append("Alias: `jev-latest` (estable) y `jev-preview`. Fija el ID con versión (`jev-1.13.0`) si ajustas umbrales de confianza.")
    return tool_result("\n".join(lines), structured={"models": models})


TOOLS = [
    {
        "name": "ask_jev",
        "description": (
            "Haz una o varias preguntas TIPADAS sobre un estado y recibe decisiones estructuradas "
            "(no texto generado). Tipos: choice (elige una opción de una lista), score (coloca el estado "
            "en una escala ordenada) y noul (probabilidad de que una afirmación sea verdadera). "
            "Pregunta cosas atómicas: si dependen de varios factores, manda una pregunta por factor y "
            "combina tú los resultados. Manda TODAS las preguntas que puedas necesitar en la MISMA llamada "
            "(se evalúan en paralelo y añadir preguntas apenas cuesta). Si una pregunta depende de la "
            "respuesta anterior, haz una segunda llamada."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {
                    "description": "El contenido a evaluar: texto, objeto JSON o lista de textos.",
                    "anyOf": [{"type": "string"}, {"type": "object"}, {"type": "array"}],
                },
                "questions": {
                    "type": "object",
                    "description": (
                        "Mapa 'id_de_pregunta' -> pregunta. Cada pregunta: {type: choice|score|noul, "
                        "instructions: '...', criteria: ...}. En choice, criteria es un objeto "
                        "{opcion: descripcion}. En score, una lista ordenada de niveles. En noul, opcional "
                        "{'true': '...', 'false': '...'}. Para señalar un campo del estado usa su ruta con "
                        "comillas invertidas, p.ej. `ticket.messages[0].text`."
                    ),
                    "minProperties": 1,
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["choice", "score", "noul"]},
                            "instructions": {"type": ["string", "object", "array"]},
                            "criteria": {"type": ["object", "array", "null"]},
                        },
                        "required": ["type", "instructions"],
                    },
                },
                "model": {"type": "string", "description": f"Modelo o alias (por defecto {DEFAULT_MODEL})."},
            },
            "required": ["state", "questions"],
        },
    },
    {
        "name": "list_jev_models",
        "description": "Lista los modelos y alias de Jev que acepta tu cuenta (GET /v1/models).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Jev decide, no escribe. Usa ask_jev para juicios que tu código pueda consumir "
                    "(enrutar, clasificar, medir, comprobar) en vez de pedir prosa a un modelo y parsearla."
                ),
            },
        }
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "ask_jev":
            return {"jsonrpc": "2.0", "id": mid, "result": call_ask_jev(args)}
        if name == "list_jev_models":
            return {"jsonrpc": "2.0", "id": mid, "result": call_list_models(args)}
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32602, "message": f"Herramienta desconocida: {name}"},
        }
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Método no soportado: {method}"}}


def main():
    log(f"arrancando {SERVER_NAME} v{SERVER_VERSION} (base {BASE_URL}, modelo por defecto {DEFAULT_MODEL})")
    if not api_key():
        log("AVISO: TYPESAFE_API_KEY no está definida; ask_jev devolverá un error de autenticación.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log("línea no-JSON ignorada")
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
