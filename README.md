# jev-mcp — Jev (TypeSafe) como herramienta para tus agentes

Servidor **MCP** mínimo (Python estándar, sin dependencias) que expone el modelo **Jev** de TypeSafe
a cualquier agente: Claude Code, Codex, Cursor, Hermes, los agentes que lanzas desde **Orca**, etc.

¿Para qué? Para tomar decisiones que tu código pueda consumir — clasificar, enrutar, medir, verificar —
sin pedirle prosa a un LLM y luego parsearla.

```
Tú: "clasifica este ticket y dime si es urgente"
   ▼
Claude Code / Codex / Hermes / los agentes que lanza Orca
   ▼  MCP (JSON-RPC por stdio, proceso local en tu máquina)
jev-mcp/server.py + run.sh          ← este repositorio
   ▼  HTTPS con Bearer TYPESAFE_API_KEY
api.typesafe.ai/v1/systemone        ← esto lo documenta TypeSafe
   ▼  respuestas tipadas: choice / score / noul + probabilidades + confianza
```

Ojo con la confusión habitual: **TypeSafe documenta la API, no un MCP** — no publica servidor MCP
oficial (solo SDKs y una skill para agentes). Este repositorio es la pieza que los une: un programa
local que traduce «herramienta `ask_jev` con estos argumentos» a una llamada HTTP a su API.

## Instalación rápida

```bash
git clone https://github.com/<usuario>/jev-mcp.git
cd jev-mcp
cp .env.example .env      # y pega tu clave de https://console.typesafe.ai/keys dentro
bash smoke_test.sh        # handshake + tools/list + una llamada real
```

Registrarlo en tu agente (ejemplo con Claude Code; en el README más abajo van Codex y Hermes):

```bash
claude mcp add jev --scope user -- /ruta/a/jev-mcp/run.sh
claude mcp list           # tiene que decir: jev ✔ Connected
```

## Por qué hay un `run.sh` y no solo el `server.py`

Varios MCP de Jev hechos por terceros reportan el mismo fallo: **algunos clientes MCP filtran las
variables de entorno al arrancar el servidor**, la clave desaparece en silencio y el servidor arranca
bien pero falla en cada llamada. Aquí la clave se lee de `jev-mcp/.env` (que está en `.gitignore`),
así que no depende del entorno y no se repite en cada configuración de cada agente.

## La idea en una frase

Jev no escribe: recibe un `state` (texto o JSON) y una lista de **preguntas tipadas**, y devuelve
**valores tipados con su probabilidad**. Sirve para decisiones que tu código consume — enrutar,
clasificar, medir, comprobar — sin pedir prosa a un LLM y luego parsearla.

- **choice** — elige una opción de una lista → `choice`, `probabilities`, `confidence`
- **score** — coloca el estado en una escala ordenada → `score`, `legend`, `probabilities`, `confidence`
- **noul** — probabilidad de que una afirmación sea cierta → `noul` (sin `confidence`)

Se pueden mezclar las tres en una sola llamada: se evalúan en paralelo y en aislamiento, así que
**añadir preguntas casi no cuesta tiempo** (y cuesta solo los tokens de esas preguntas).

## Instalación

No hay nada que instalar: es un único fichero que solo usa la biblioteca estándar.

```bash
export TYPESAFE_API_KEY=sk-...        # se saca en https://console.typesafe.ai/keys
python3 server.py                     # habla MCP por stdio (lo lanza el cliente, no tú)
```

Probarlo sin configurar nada:

```bash
bash smoke_test.sh                    # handshake + tools/list + una llamada real
```

## Conectar el MCP a tu agente

Configuración típica (Claude Code, Codex, Cursor, Hermes y demás clientes MCP):

```json
{
  "mcpServers": {
    "jev": {
      "command": "python3",
      "args": ["/ruta/absoluta/jev-mcp/server.py"],
      "env": { "TYPESAFE_API_KEY": "sk-..." }
    }
  }
}
```

- **Claude Code:** `claude mcp add jev -- python3 /ruta/jev-mcp/server.py` (con `TYPESAFE_API_KEY` en el entorno).
- **Hermes:** añadirlo en la configuración de MCP del perfil.
- **Orca:** los agentes que lanza leen su propia configuración MCP, así que se registra en el agente
  (Claude Code, Codex…), no en Orca. Alternativa: la **skill oficial** de TypeSafe, que enseña al
  agente a usar la API sin MCP → `npx skills add typesafe-ai/skills --skill typesafe-ai`.

## Herramientas que expone

| Herramienta | Para qué |
| --- | --- |
| `ask_jev` | Estado + preguntas tipadas → respuestas con probabilidades y confianza |
| `list_jev_models` | Modelos y alias que acepta la cuenta |

## Cómo pedirlo bien (esto es la mitad del valor)

1. **Una pregunta, un juicio atómico.** «¿Este mensaje expresa urgencia?» sí; «analiza esto y decide
   qué hacer» no. Si el juicio depende de varios factores, manda una pregunta por factor y combina tú
   los resultados con pesos tuyos.
2. **Manda de más en una sola llamada.** Preguntar algo que solo importa en algunos casos sale casi
   gratis; que el agente decida después si usa la respuesta.
3. **Noul para sí/no, Score para medir.** Un noul de 0,5 significa «no lo sé», no «nivel medio».
4. **Señala los campos del estado** con su ruta entre comillas invertidas: `` `ticket.messages[0].text` ``.
5. **Confianza en tres bandas:** alta → actúa; media → confirma o revisa; baja → a una persona.
6. **Segunda llamada solo cuando de verdad depende** de la primera respuesta (para traer más datos,
   elegir las opciones siguientes…).

## Límites y coste (verificado 18-sep-2026)

- Modelo `jev-1.13.0` (alias `jev-latest`), **0,042 $/Mtok** de entrada, salida gratis.
- 64k tokens por petición; 32k para el `state` + la pregunta más larga.
- Límites: 250k tokens/s y 1.200 peticiones/min (ajustándose, pueden cambiar).
- Solo texto; el inglés rinde mejor que el resto de idiomas.
- Errores: 401/403 clave, 422 validación, 429 límite, 529 sobrecarga (reintentar con backoff).

## Qué NO es

Jev no puede ser el modelo de un agente: no genera texto ni razona en prosa. Es una **herramienta**
del agente — el agente razona, Jev decide.
