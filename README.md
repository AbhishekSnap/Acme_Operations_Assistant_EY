# Acme Operations Assistant

Agentic enterprise assistant for Acme Operations — EY Applied AI Engineer Technical Assessment.

---

## Quick Start

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
```

The app is available at **http://localhost:8000**.  
Keycloak admin console: **http://localhost:8080** (admin / admin).

Demo users (password: `Acme@2026!`):

| Username | Role | Permissions |
|---|---|---|
| alice | sales_user | read |
| bob | support_user | read, update_issue |
| carol | admin | read, update_issue, create_next_action |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Docker Compose Network: acme-net                                    │
│                                                                      │
│  ┌──────────┐  bearer token  ┌──────────────────────────────────┐   │
│  │ Browser  │───────────────▶│  FastAPI app  (port 8000)        │   │
│  │ (HTML UI)│◀───────────────│  /auth/token  (Keycloak OIDC)   │   │
│  └──────────┘                │  /chat        (agent endpoint)   │   │
│                              │  /skills/*    (skill endpoints)  │   │
│                              │  /admin/traces                   │   │
│                              └──────────┬───────────────────────┘   │
│                                         │                           │
│                ┌────────────────────────┼──────────────┐            │
│                ▼                        ▼              ▼            │
│  ┌──────────────────┐  ┌─────────────────────┐  ┌──────────────┐   │
│  │  Claude API      │  │ MCP Server (8001)    │  │  Keycloak    │   │
│  │  claude-sonnet   │  │  acme-mcp container  │  │  (port 8080) │   │
│  │  Tool-use loop   │  │  /tools  (schemas)   │  │  realm: acme │   │
│  └──────────────────┘  │  /tools/call         │  │  3 roles     │   │
│                        │  /mcp/sse            │  └──────────────┘   │
│                        └──────────┬───────────┘                     │
│                                   │ SQL                             │
│           ┌───────────────────────┼──────────┐                      │
│           ▼                       ▼          ▼                      │
│  ┌──────────────┐    ┌──────────────────┐  ┌──────────────────┐    │
│  │  PostgreSQL  │    │     Redis        │  │  Observability   │    │
│  │  (port 5432) │    │  (port 6379)     │  │  JSONL traces    │    │
│  │  customers   │    │  session state   │  │  ./logs/         │    │
│  │  issues      │    │  cached lookups  │  └──────────────────┘    │
│  │  issue_upds  │    │  tool results    │                          │
│  │  next_actions│    └──────────────────┘                          │
│  │  users       │                                                   │
│  └──────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### Component responsibilities

| Component | Role |
|---|---|
| **FastAPI app** | API gateway, auth middleware, agent orchestration, static UI |
| **MCP Server** | Owns all tool definitions and SQL; exposes them via HTTP + SSE |
| **Claude API** | Reasoning engine — selects tools dynamically based on query |
| **Keycloak** | OIDC token issuer; realm `acme` imported at startup |
| **PostgreSQL** | Durable store: customers, issues, updates, next actions |
| **Redis** | Volatile store: session history (TTL 1h), cached tool results (TTL 2m) |

---

## Agent Design

The agent uses **Claude's native tool-use** (not LangChain). The loop:

1. Build messages: Redis session history + current query
2. Call Claude with the tool schemas fetched from the MCP server
3. Claude returns `tool_use` blocks → execute each via MCP HTTP call
4. Tool results appended as `tool_result` blocks → loop
5. On `end_turn` or `stop_reason=end_turn` → return final text

Tool schemas live entirely in the MCP server. The agent core has no hard-coded SQL.

### Skills

The **Customer Escalation Summary Skill** (`app/skills/escalation.py`) is a structured,
multi-step LLM workflow distinct from a one-off prompt:

1. Detects escalation intent via regex
2. Calls `get_customer_profile` + `get_open_issues` via MCP
3. Feeds structured data into a focused summarisation prompt
4. Returns a formatted brief (overview, issues table, risks, actions)

It can be triggered automatically by the agent or called directly via `POST /skills/escalation`.

---

## MCP (Model Context Protocol)

**Why MCP here?**  
MCP decouples tool *definitions* from the *agent core*. The FastAPI app fetches schemas
from `GET /tools` at startup — adding a new tool to the MCP server requires no changes
to the agent. In a larger deployment, multiple agents (different models, different tenants)
could share one MCP server.

**Implementation**: HTTP transport with a `/mcp/sse` SSE endpoint for streaming tool lists.
The MCP server runs as its own container (`acme-mcp`) — isolation means tool code
(which touches the database) is separate from agent orchestration logic.

---

## Authentication & RBAC

Keycloak issues RS256-signed JWTs. The app validates them locally (JWKS fetch) — no
introspection round-trip per request.

| Role | Permissions |
|---|---|
| sales_user | read |
| support_user | read, update_issue |
| admin | read, update_issue, create_next_action |

RBAC is enforced at two layers:
1. **Agent system prompt** - tells Claude what the user's role permits
2. **MCP layer** - `update_issue` and `create_next_action` are blocked in the MCP server if the
   user's role lacks the permission, regardless of what the agent requests

---

## Redis vs PostgreSQL — Trade-off

| What | Where | Why |
|---|---|---|
| Customer/issue records | PostgreSQL | Durable, transactional, auditable |
| Conversation history | Redis (TTL 1h) | Volatile; 20-turn window sufficient; fast read/write |
| Tool result cache | Redis (TTL 2m) | Repeated identical queries within a session skip DB |
| Session preferences | Redis | User-scoped, low-durability, fast |

On Redis restart the app degrades gracefully — cache misses fall back to the database.

---

## Observability

All events are written as newline-delimited JSON to `./logs/traces.jsonl`:

- `tool_call` — tool name, args, result keys, latency_ms
- `llm_turn` — role, content summary, latency_ms  
- `request_complete` — user, query, tools used, total latency, error

View traces: `GET /admin/traces` (requires any authenticated user).

**Bonus**: The tracer is structured so an OpenTelemetry exporter can be dropped in by
replacing `write_event` with an OTLP span emit.

---

## Evaluation

```bash
# Install dependency (one-time)
pip install httpx

# App must be running first
python eval/run_eval.py
# or against Docker:
python eval/run_eval.py --base-url http://localhost:8000
```

10 test questions covering:
- Tool selection correctness (Q01, Q02, Q03, Q06, Q10)
- Data grounding — expected strings in response (all Qs)
- RBAC enforcement (Q04 admin allowed, Q05 sales_user blocked)
- Multi-step chained tool use (Q10)
- Out-of-scope graceful decline (Q09)
- Escalation skill (Q06)

Results written to `eval/eval_results.json`.

---

## Trade-offs & Documented Shortcuts

| Decision | Shortcut taken | Production alternative |
|---|---|---|
| Streaming | Chunked simulation via SSE | Full async streaming with `stream=True` in Anthropic SDK |
| Tool auth | Permission check in runner + agent prompt | Separate authz service / OPA policy |
| Keycloak | Dev-mode (`start-dev`) | Production config: external DB, TLS, replica |
| Observability | JSONL files | OpenTelemetry + collector + Jaeger/Datadog |
| Session memory | Last 20 turns in Redis | Vector store for semantic recall over long histories |
| MCP transport | HTTP+SSE | stdio transport for local in-process tools |

---

## AI Tool Usage Notes

This solution was built with **Claude Code** as the primary AI coding assistant.

**Delegated to AI:**
- Scaffolding boilerplate (Dockerfiles, requirements, `__init__.py` files)
- FastAPI route patterns and Pydantic model structure
- SQL schema and seed data generation
- JWT validation pattern with `python-jose`

**Reviewed and corrected by hand:**
- Agent tool-use loop logic (iteration cap, message format for `tool_result`)
- RBAC enforcement — verified the two-layer approach (prompt + code) was correct
- Redis TTL values — chosen based on use-case reasoning, not AI suggestion
- Keycloak realm JSON — tested against actual Keycloak behaviour

**Would not trust AI for without oversight on a client engagement:**
- Security-critical paths (token validation, RBAC enforcement)
- Database schema migrations on live data
- Any code that touches PII or compliance-sensitive data
- Infrastructure-as-code for production environments

---

## Project Structure

```
.
├── docker-compose.yml
├── .env.example
├── app/
│   ├── main.py              # FastAPI app, lifespan, middleware
│   ├── config.py            # Pydantic settings (env vars)
│   ├── auth/
│   │   └── keycloak.py      # JWT validation, RBAC helpers
│   ├── agent/
│   │   ├── runner.py        # Claude tool-use loop
│   │   └── mcp_client.py    # HTTP client for MCP server
│   ├── skills/
│   │   └── escalation.py    # Customer Escalation Summary Skill
│   ├── api/
│   │   ├── routes.py        # /chat, /skills, /admin endpoints
│   │   └── auth_routes.py   # /auth/token (demo login helper)
│   ├── db/
│   │   └── database.py      # asyncpg connection pool
│   ├── cache/
│   │   └── redis_client.py  # Session memory + cache helpers
│   └── observability/
│       └── tracer.py        # JSONL trace writer
├── mcp_server/
│   └── main.py              # MCP server: tool schemas + SQL execution
├── infra/
│   ├── keycloak/
│   │   └── acme-realm.json  # Realm import: roles, clients, users
│   └── postgres/
│       └── init.sql         # Schema + seed data
├── acme-ui/
│   ├── src/
│   │   ├── App.jsx          # React UI with dark/light theme and markdown renderer
│   │   └── App.css          # EY-branded CSS custom properties
│   └── package.json
└── eval/
    ├── questions.json        # 10 test questions
    ├── run_eval.py           # Evaluation runner
    └── eval_results.json     # Latest results (generated)
```
