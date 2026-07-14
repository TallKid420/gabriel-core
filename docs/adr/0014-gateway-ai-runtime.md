# ADR-014: Gateway AI Runtime — Providers, Streaming Chat, Tools, Sessions

- **Status:** Accepted
- **Date:** 2026-07-13
- **Phase:** 3 — Gateway AI Runtime
- **Builds on:** ADR-011 (Agent Specification Migration), ADR-013 (Core
  Business Logic — conversations, messages, agent management)

## Context

Phases 1–2 delivered the platform foundations (Universal Resources, GRNs,
tenancy, auth, PEEL) and the core domain objects (conversations, messages,
agents). What was missing was the piece that makes Gabriel *do* anything:
an AI runtime that takes a user turn on a conversation, routes it to an LLM
according to the conversation's agent configuration, streams the answer back,
executes tools the model requests, and persists the exchange through the
Phase-2 services.

Requirements shaping this phase:

- Local-first: **Ollama** is the first (and default) provider, but the
  abstraction must accommodate OpenAI/Anthropic-style hosted APIs later
  without touching the runtime.
- The Gateway **owns no persistent business data** — conversations, messages
  and agents remain the Phase-2 slices' responsibility; the Gateway only
  orchestrates.
- Streaming must reuse the platform's existing SSE conventions
  (`text/event-stream`, `StreamingResponse`) already used by `/events/stream`.

## Decision

New package `gabriel.gateway` with six cooperating parts:

### 1. LLM provider abstraction (`gateway/providers/base.py`)

`LLMProvider` is a `Protocol` (structural typing — no inheritance required):

- `chat_completion(messages, *, model, ...) -> ChatCompletionResult`
- `stream_chat_completion(...) -> AsyncIterator[StreamChunk]`
- `list_models() -> list[ModelInfo]`
- `health_check() -> ProviderHealth`

Shared dataclasses (`ChatMessage`, `ToolCallRequest`, `TokenUsage`,
`StreamChunk`, …) form the provider-neutral wire format; every provider maps
its native API to them. A typed error hierarchy (`ProviderError`,
`ProviderConnectionError`, `ModelNotFoundError`) lets the runtime degrade
gracefully — an unreachable Ollama daemon surfaces as a clean SSE `error`
event / HTTP 502, never a stack trace.

`ProviderRegistry` (`gateway/providers/registry.py`) holds named providers
with a configurable default (`ollama`). `register_default_providers()` wires
the out-of-the-box set at app startup, honouring `GABRIEL_OLLAMA_BASE_URL`.

### 2. Ollama provider (`gateway/providers/ollama.py`)

Speaks Ollama's native `/api/chat` (streaming NDJSON and buffered),
`/api/tags` (model listing) and `/api/version` (health). Token usage is read
from `prompt_eval_count` / `eval_count`; native `tool_calls` are mapped to
`ToolCallRequest`. The `httpx` transport is injectable so tests run against
`httpx.MockTransport` — no daemon needed.

### 3. Prompt assembly (`gateway/prompt.py`)

`PromptStrategy` is a protocol; `DefaultPromptStrategy` builds
`system prompt (+ injected context blocks) → windowed history → user turn`,
dropping stale system messages from history and windowing to the last N
turns (default 20). The assembler is constructor-injected into the runtime,
so RAG-style strategies can be swapped in later without runtime changes.

### 4. Tool execution framework (`gateway/tools.py`)

`RuntimeTool` (name / description / JSON-schema parameters / `run`) with
`to_llm_spec()` producing the OpenAI-compatible function spec that both
Ollama and hosted providers understand. `RuntimeToolRegistry` scopes what an
agent may call (an agent's declared `tools` list restricts it; none declared
= all runtime tools). Built-in: `current_datetime`. `FunctionTool.
from_function_registry` bridges the pre-existing governed function registry
so Phase-4 governed tools can be surfaced to the LLM without duplication.
`execute_tool_call()` never raises — failures come back as structured tool
results the model can react to.

### 5. Chat runtime + SSE endpoint (`gateway/service.py`, `api/routers/gateway.py`)

`ChatRuntimeService.stream_turn()` is one async generator emitting SSE
frames: `session → message (persisted user turn) → token* →
(tool_call → tool_result)* → done | error`. The tool loop is bounded
(`MAX_TOOL_ITERATIONS = 4`); tool results are fed back as `tool`-role
messages and also persisted for audit. The assistant message is persisted
with model, provider and token usage metadata via the Phase-2
`MessageService`, so usage tracking rides on the existing message store.
`complete_turn()` reuses the same pipeline buffered for `POST /gateway/chat`.

Endpoints (all PEEL-enforced via new `gateway:*` capability mappings):

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/gateway/chat/stream` | SSE streaming chat turn |
| `POST /api/v1/gateway/chat` | Buffered chat turn |
| `GET /api/v1/gateway/providers` | Providers + live health |
| `GET /api/v1/gateway/providers/{name}/models` | Models on a provider |
| `GET /api/v1/gateway/tools` | Runtime tool specs |
| `GET /api/v1/gateway/sessions` | Active sessions (org-scoped) |
| `DELETE /api/v1/gateway/sessions/{id}` | End a session |

### 6. Ephemeral sessions (`gateway/sessions.py`)

`SessionManager` tracks live chat sessions in memory, keyed by
`(org, principal, conversation)`, with a 30-minute idle TTL and lazy
eviction. Sessions are deliberately **not persisted**: they are runtime
liveness state, while durable context already lives in conversations and
messages. This keeps the Gateway stateless across restarts.

## No database migration

Phase 3 adds **no Alembic migration**. Sessions are ephemeral by design, and
every durable artifact of a chat turn (user / assistant / tool messages,
token usage, model metadata) fits the Phase-2 `messages` and `conversations`
tables, which already carry `usage`, `model` and JSON `metadata` columns.

## Middleware fix

The request-logging middleware previously monkeypatched `request._receive`
to replay the consumed body indefinitely. Starlette's `BaseHTTPMiddleware`
already replays a consumed body to the downstream app; the extra
`http.request` frames crashed streaming responses waiting on
`http.disconnect`. The patch was removed — required for `POST` SSE
endpoints to work at all.

## Consequences

- Adding OpenAI/Anthropic = one provider class + one `registry.register()`
  call; agents opt in via their spec's `provider` / `model` fields
  (per-agent, config-driven routing already works today).
- Clients get a single SSE contract (`session/message/token/tool_call/
  tool_result/done/error`) independent of the underlying provider.
- In-memory sessions mean horizontal scaling will eventually need a shared
  session store (e.g. Redis) — acceptable for the current single-node
  deployment and isolated behind `SessionManager`.
- Tool execution inside the runtime is currently limited to registered
  runtime tools; deep integration with the governed `ToolExecutor`
  (approvals, audit events) is Phase-4 work, pre-bridged via
  `FunctionTool.from_function_registry`.

## Testing

51 new tests: provider registry + Ollama over `httpx.MockTransport`
(12), prompt assembly, tool framework, session manager (21), chat runtime
with a scriptable `FakeProvider` — persistence, tool loop, history
windowing, error paths (9), and end-to-end API tests including true SSE
streaming through the middleware stack (9). Full suite: 503 passed with
only the 20 pre-existing legacy failures from before Phase 2.
