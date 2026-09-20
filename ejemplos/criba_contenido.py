#!/usr/bin/env python3
"""Criba de contenido con Jev: puntua los cuatro ejes de la rubrica de Codeia en una sola llamada.

Uso:
    python3 criba_contenido.py <nota.md> [<nota2.md> ...]      # una o varias notas del vault
    python3 criba_contenido.py --texto "..." --titulo "..."     # un candidato suelto
    python3 criba_contenido.py <nota.md> --sin-comparar         # no busca la puntuacion manual

Lee el estado de la nota (frontmatter + cuerpo), pregunta los cuatro ejes como Score 0-5,
suma los puntos (0-20), aplica la regla (>=15 publica / 10-14 cola / <10 descarta) y marca
para revision humana si alguna confianza baja del umbral.

La clave de TypeSafe se lee del .env via run.sh, nunca de la linea de comandos.
"""
import argparse
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(os.path.dirname(AQUI), "run.sh")

# Umbral de confianza por debajo del cual la pieza va a revision humana.
UMBRAL_CONFIANZA = 0.60

# El estado es la mitad del trabajo: Jev no puede juzgar lo que no esta en el estado.
# Estos ejes dependen de NUESTRO contexto, asi que el contexto viaja con el candidato.
CABECERA_CONTEXTO = """CONTEXTO (Codeia, {hoy}):
- Audiencia: desarrolladores en espanol que ya usan agentes e IA aplicada.
- Podemos probar y medir las herramientas en nuestro propio stack (Codeia, Hermes, MCP propio, Zernio),
  asi que una prueba propia siempre es viable para nosotros.
- Publicamos unas 2 piezas por semana; la actualidad se mide contra la fecha de la fuente.
- El contenido es de analisis y prueba, no anuncios de producto.

CANDIDATO A CRIBAR:
"""

# La rubrica de Codeia, tal cual: cuatro ejes de 0 a 5, suma sobre 20.
RUBRICA = {
    "encaje": {
        "instrucciones": "Cuanto le importa este tema a nuestra audiencia (desarrolladores que usan agentes e IA aplicada)",
        "criterios": [
            "Nada, es de otro mundo",
            "Poco, nicho ajeno",
            "Interesa de refilon",
            "Interesa al publico general de IA",
            "Interesa mucho a nuestro publico",
            "Es exactamente nuestro publico",
        ],
    },
    "verificable": {
        "instrucciones": "Cuanta fuente solida y citable hay detras",
        "criterios": [
            "Solo un tuit, un video o nada",
            "Anuncio del fabricante sin datos",
            "Documentacion oficial del proyecto",
            "Repositorio publico documentado",
            "Repositorio con datos medibles",
            "Datos reproducibles medidos por terceros",
        ],
    },
    "angulo": {
        "instrucciones": "Cuanto podemos aportar nosotros de mas (prueba propia, criterio, experiencia real)",
        "criterios": [
            "Nada, ya esta todo dicho",
            "Contariamos lo mismo que todos",
            "Un comentario breve",
            "Un enfoque propio",
            "Una prueba propia que nadie ha hecho",
            "Cambiamos el marco del debate",
        ],
    },
    "actualidad": {
        "instrucciones": "Como de fresco esta el tema",
        "criterios": [
            "Tema viejo o ya resuelto",
            "De hace meses",
            "Del mes pasado",
            "De esta semana",
            "De estos dias",
            "Es el tema del dia",
        ],
    },
}


def ask_jev(state, questions):
    """Habla con el MCP de Jev por stdin/stdout (JSON-RPC) y devuelve las respuestas."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "criba-codeia", "version": "1.0"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "ask_jev", "arguments": {"state": state, "questions": questions}}},
    ]
    entrada = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs)
    p = subprocess.run(["bash", RUN], input=entrada, capture_output=True, text=True, timeout=180)
    for linea in p.stdout.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            m = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if m.get("id") == 2:
            return m["result"].get("structuredContent", {})
    return {"error": (p.stderr or "sin respuesta")[-500:]}


def preguntas():
    q = {}
    for nombre, cfg in RUBRICA.items():
        q[nombre] = {"type": "score", "instructions": cfg["instrucciones"], "criteria": cfg["criterios"]}
    return q


def leer_nota(ruta):
    """Devuelve (titulo, manual, estado) leyendo frontmatter y cuerpo de la nota."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    titulo = os.path.splitext(os.path.basename(ruta))[0]
    manual = {}
    if texto.startswith("---"):
        fin = texto.find("\n---", 3)
        if fin > 0:
            for linea in texto[3:fin].splitlines():
                if ":" in linea:
                    k, v = linea.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k in ("encaje", "verificable", "angulo", "actualidad", "puntos", "titulo", "title"):
                        manual[k] = v
    manual = {k: v for k, v in manual.items() if re.fullmatch(r"\d+", str(v))}
    return titulo, manual, texto[:8000]


def cribar(titulo, estado):
    from datetime import date
    estado_completo = CABECERA_CONTEXTO.format(hoy=date.today().isoformat()) + estado
    datos = ask_jev(estado_completo, preguntas())
    if "error" in datos:
        print(f"  ERROR: {datos['error']}")
        return None
    return datos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("notas", nargs="*")
    ap.add_argument("--texto")
    ap.add_argument("--titulo", default="candidato")
    ap.add_argument("--sin-comparar", action="store_true")
    args = ap.parse_args()

    piezas: list[tuple[str, dict, str]] = []
    if args.texto:
        piezas.append((args.titulo, {}, args.texto))
    for ruta in args.notas:
        piezas.append(leer_nota(ruta))
    if not piezas:
        print("Nada que cribar: pasa notas o --texto.")
        return 1

    print(f"{'candidato':<34} {'encaje':>6} {'verif':>6} {'angulo':>6} {'actual':>7} {'PUNTOS':>7} {'decision':<12} {'conf.min':>8}")
    print("-" * 108)
    for titulo, manual, estado in piezas:
        datos = cribar(titulo, estado)
        if not datos:
            continue
        respuestas = datos.get("answers", {})
        valores, confianzas = {}, []
        for eje in RUBRICA:
            d = respuestas.get(eje, {})
            valores[eje] = d.get("score")
            if d.get("confidence") is not None:
                confianzas.append(d["confidence"])
        suma = sum(v for v in valores.values() if isinstance(v, (int, float)))
        conf_min = min(confianzas) if confianzas else 0.0
        decision = "publicar" if suma >= 15 else ("cola" if suma >= 10 else "descartar")
        if conf_min < UMBRAL_CONFIANZA:
            decision = "REVISION"
        manual_txt = ""
        if manual and not args.sin_comparar:
            m = manual.get("puntos")
            if m:
                diff = suma - float(m)
                manual_txt = f"   (a mano: {m} | dif: {diff:+.0f})"
        print(f"{titulo[:33]:<34} {valores['encaje']!s:>6} {valores['verificable']!s:>6} "
              f"{valores['angulo']!s:>6} {valores['actualidad']!s:>7} {suma:>7.1f} {decision:<12} {conf_min:>8.2f}{manual_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
