# Gabriel

**Gabriel** is an enterprise AI operating system: a multi-tenant platform for building,
governing, and running AI agents grounded in an organization's own knowledge. This
repository — `gabriel-core` — is the Python/FastAPI backend. The companion
[`gabriel-desktop`](https://github.com/TallKid420/gabriel-desktop) repository provides
the Next.js web/desktop client.

Every entity in Gabriel is a **Universal Resource** with a global resource name (GRN),
every mutation flows through an **event store**, and every request is authorized by the
**PEEL** policy engine. On top of that foundation Gabriel provides conversations,
governed AI agents, an LLM gateway with streaming chat and tools, and document-grounded
retrieval-augmented generation (RAG).

- **Architecture overview:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **API reference:** [`docs/API.md`](docs/API.md)
- **Design decisions:** [`docs/adr/`](docs/adr/) (ADR-0012 … ADR-0015)
- **Merge sequence for the phased PRs:** [`docs/MERGE_ORDER.md`](docs/MERGE_ORDER.md)

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python**  | 3.11+   | The codebase targets 3.11. |
| **PostgreSQL** | 16+ **with the `pgvector` extension** | Required for vector similarity search. Use the `pgvector/pgvector` image or install the extension manually. |
| **Ollama**  | latest  | Local LLM + embedding runtime. Provides chat models and the `nomic-embed-text` embedding model. |
| **Node.js / pnpm** | Node 20+, pnpm 11+ | Only needed for the `gabriel-desktop` frontend. |

The fastest way to get PostgreSQL (with pgvector) and Ollama running locally is the
bundled Docker Compose stack — see [Quickstart with Docker Compose](#quickstart-with-docker-compose).

---

## Quickstart with Docker Compose

The repository ships a [`docker-compose.yml`](docker-compose.yml) that runs the two
external dependencies — **PostgreSQL + pgvector** and **Ollama** — with health checks.
The application itself runs on the host (so you get fast reloads and easy debugging).

```bash
# 1. Start Postgres (with pgvector) and Ollama
docker compose up -d

# 2. Wait for both to become healthy
docker compose ps

# 3. Pull the models Gabriel uses by default
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```

This gives you:

- PostgreSQL on `localhost:5432` — database `gabriel_core`, user `postgres`, password `postgres`
  (matches the default connection string, see below).
- Ollama on `localhost:11434`.

---

## Environment setup

Gabriel is configured through `GABRIEL_*` environment variables. Copy the block below
into a `.env` file at the repository root and adjust as needed. (Load it into your
shell with e.g. `set -a; source .env; set +a`.)

```dotenv
# --- Runtime environment ---
GABRIEL_ENV=development                 # "development" | "production"

# --- Database ---
# The application uses an async driver; Alembic uses a sync driver.
# The bundled docker-compose Postgres matches these defaults.
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/gabriel_core

# --- Authentication / JWT ---
GABRIEL_DEV_AUTH_ENABLED=true           # dev login provider (/auth/dev/*); disable in prod
GABRIEL_JWT_TOKEN_TTL_SECONDS=3600
GABRIEL_SESSION_COOKIE_NAME=gabriel_session
GABRIEL_SESSION_COOKIE_SECURE=false     # defaults to true when GABRIEL_ENV=production
# Optional PEM key paths. When unset an ephemeral key is generated at startup
# (fine for dev/test; set real keys in production).
# GABRIEL_JWT_PRIVATE_KEY_PATH=/path/to/private.pem
# GABRIEL_JWT_PUBLIC_KEY_PATH=/path/to/public.pem

# --- LLM gateway (Ollama) ---
GABRIEL_OLLAMA_BASE_URL=http://localhost:11434

# --- Embeddings / RAG ---
GABRIEL_EMBEDDING_MODEL=nomic-embed-text   # 768-dimensional embeddings
GABRIEL_CHUNK_SIZE=512                      # tokens per chunk
GABRIEL_CHUNK_OVERLAP=64                    # token overlap between chunks
GABRIEL_CONTENT_ROOT=.gabriel/content       # where uploaded file bytes are stored
# GABRIEL_PGVECTOR_URL=...                   # optional: separate URL for vector tools

# --- Agent specifications ---
# GABRIEL_AGENT_SPECS_DIR=./agent-specs
# GABRIEL_DEFAULT_ORG_ID=...                 # org used for agent-spec GRN resolution
```

> **Note on the database URL.** `gabriel-core` currently reads its default connection
> string from `src/gabriel/database/session.py`
> (`postgresql+asyncpg://postgres:postgres@localhost/gabriel_core`) and Alembic reads
> `sqlalchemy.url` from `alembic.ini`
> (`postgresql+psycopg2://postgres:postgres@localhost/gabriel_core`). The docker-compose
> defaults are chosen to match both. If Postgres is unreachable at startup, the API
> falls back to a local SQLite database under `.gabriel/` so you can still explore the
> app without Postgres — but vector search requires PostgreSQL + pgvector.

---

## Installing dependencies

```bash
# From the repository root, in a Python 3.11 virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -e .            # installs gabriel-core and its dependencies (see pyproject.toml)
# or: pip install -r requirements.txt
```

---

## Database migrations

Migrations are managed with **Alembic**. With PostgreSQL running (and pgvector
available), apply all migrations:

```bash
alembic upgrade head
```

The final migration (`k1e5f7a9b3c4`) creates the document/knowledge tables and, **on
PostgreSQL only**, enables the `vector` extension, adds the `vector(768)` embedding
column, and builds an HNSW cosine index. To roll back one step:

```bash
alembic downgrade -1
```

To inspect the SQL without executing it:

```bash
alembic upgrade head --sql
```

---

## Running the dev server

```bash
# The package lives under src/, installed editable above.
uvicorn gabriel.api.app:app --reload --port 8000
```

Then open:

- **API docs (Swagger UI):** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

> These URLs are for the machine running the server. If you are running the server on a
> remote/sandbox VM, substitute that host's address.

### Running the frontend (optional)

In the `gabriel-desktop` repository:

```bash
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_GATEWAY_URL=http://localhost:8000 \
pnpm dev            # serves the web client on http://localhost:3000
```

---

## Running tests

```bash
pytest                       # full suite
pytest tests/knowledge -q    # a single slice
pytest tests/api -q          # API integration tests
```

The test suite runs entirely against an in-memory / on-disk **SQLite** database and
uses mock transports for Ollama, so **no PostgreSQL or Ollama instance is required** to
run tests. Vector similarity falls back to an in-process cosine implementation on
SQLite, and embedding calls degrade gracefully when Ollama is not reachable.

---

## End-to-end smoke test

This walkthrough exercises the full stack — auth → agent → conversation → streaming
chat → document upload → RAG — using `curl`. Start Postgres + Ollama (with `llama3.2`
and `nomic-embed-text` pulled), run migrations, and start the server first.

```bash
BASE=http://localhost:8000/api/v1
```

**1. Register (creates an organization + owner user and logs you in).**

```bash
REG=$(curl -s -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@acme.test","password":"supersecret","display_name":"Alice","organization_name":"Acme"}')
TOKEN=$(echo "$REG" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"
```

**2. (Login again later, if needed.)** Password login returns a fresh access token and
a refresh token:

```bash
curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' -d '{
  "method":"password",
  "credentials":{"email":"alice@acme.test","password":"supersecret","org_id":"<org-id-from-register>"}
}'
```

**3. Create an agent.**

```bash
AGENT=$(curl -s -X POST $BASE/agents -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "name":"Support Bot",
  "system_prompt":"You are a concise support assistant.",
  "model_config":{"model":"llama3.2"}
}')
AGENT_GRN=$(echo "$AGENT" | python -c 'import sys,json; print(json.load(sys.stdin)["grn"])')
```

**4. Start a conversation.**

```bash
CONV=$(curl -s -X POST $BASE/conversations -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title":"First chat"}')
CONV_GRN=$(echo "$CONV" | python -c 'import sys,json; print(json.load(sys.stdin)["grn"])')
```

**5. Chat with streaming (Server-Sent Events).**

```bash
curl -N -X POST $BASE/gateway/chat/stream -H "$AUTH" -H 'Content-Type: application/json' -d "{
  \"conversation_grn\":\"$CONV_GRN\",
  \"content\":\"Hello! Who are you?\"
}"
# -> a stream of SSE events: token deltas, an optional `context` event, and a final done event.
```

**6. Upload a document (it is chunked and embedded automatically).**

```bash
echo "Our refund policy allows returns within 30 days of purchase." > policy.txt
DOC=$(curl -s -X POST $BASE/documents -H "$AUTH" \
  -F 'file=@policy.txt;type=text/plain')
DOC_GRN=$(echo "$DOC" | python -c 'import sys,json; print(json.load(sys.stdin)["grn"])')
```

**7. Group the document into a knowledge source and attach it.**

```bash
SRC=$(curl -s -X POST $BASE/knowledge/sources -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Policies"}')
SRC_GRN=$(echo "$SRC" | python -c 'import sys,json; print(json.load(sys.stdin)["grn"])')

curl -s -X POST "$BASE/knowledge/sources/$SRC_GRN/documents" -H "$AUTH" \
  -H 'Content-Type: application/json' -d "{\"document_grn\":\"$DOC_GRN\"}"
```

**8. Search directly, or point the agent at the source for RAG chat.**

```bash
# Direct semantic/keyword search:
curl -s -X POST $BASE/knowledge/search -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"query":"how long do I have to return something?"}'

# Grant the agent the knowledge source so chat auto-retrieves grounding context:
curl -s -X PATCH "$BASE/agents/$AGENT_GRN" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"knowledge_sources\":[\"$SRC_GRN\"]}"

# Now a chat turn for this agent retrieves relevant chunks and emits a `context` SSE event:
curl -N -X POST $BASE/gateway/chat/stream -H "$AUTH" -H 'Content-Type: application/json' -d "{
  \"conversation_grn\":\"$CONV_GRN\",
  \"content\":\"What is our refund window?\"
}"
```

If step 8 answers using the refund policy you uploaded, the full document → embedding →
retrieval → RAG pipeline is working end to end.

> **Graceful degradation.** If Ollama is not running, chat returns a provider error and
> embeddings are skipped (documents are still stored and chunked, and search falls back
> to keyword matching) — the API never crashes because a model backend is unavailable.

---

## Repository layout

```
gabriel-core/
├── src/gabriel/
│   ├── api/            # FastAPI app, routers, middleware, dependency wiring
│   ├── identity/       # authentication, JWT, sessions
│   ├── resource/       # Universal Resources, GRNs, resource types
│   ├── policy/         # PEEL authorization, capabilities
│   ├── events/         # event store & projections
│   ├── conversation/   # conversations & messages
│   ├── agent/          # agent management & specifications
│   ├── notification/   # notifications
│   ├── memory/         # memory layers
│   ├── gateway/        # LLM runtime: providers, prompt assembly, tools, sessions
│   ├── document/       # document upload, content store, processing
│   └── knowledge/      # chunking, embeddings, vector store, sources, retrieval
├── alembic/            # database migrations
├── docs/               # architecture, API reference, ADRs, merge order
├── tests/              # pytest suite (SQLite + mock transports)
└── docker-compose.yml  # Postgres + pgvector, Ollama
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how these fit together.
