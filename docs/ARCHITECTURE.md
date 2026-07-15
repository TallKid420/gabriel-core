# Gabriel — Architecture Overview

This document describes the high-level architecture of Gabriel, the enterprise AI
operating system. It is intended for engineers who need a mental model of how the
system fits together before diving into code or a specific slice.

For the rationale behind individual decisions, see the Architecture Decision Records in
[`docs/adr/`](adr/). This overview references ADR-0012 through ADR-0015, which cover the
phases that make up the current system.

---

## 1. Three-tier design

Gabriel is organized into three cooperating tiers:

| Tier | Repository / package | Responsibility |
|------|----------------------|----------------|
| **Core** | `gabriel-core` — `resource`, `policy`, `events`, `identity`, and the domain slices | Source of truth for all data. Owns Universal Resources, the event store, authorization, and business logic. Persists everything. |
| **Gateway** | `gabriel-core` — `gabriel/gateway` package | Stateless AI runtime. Orchestrates LLM calls, streaming, tools, prompt assembly, and RAG. Owns **no** persistent business data — durable state stays in Core. |
| **Desktop** | `gabriel-desktop` (Next.js) | The user-facing web/desktop client: auth, conversations with streaming chat, agent management, document upload, notifications, settings. |

The Core and Gateway tiers both live inside the `gabriel-core` FastAPI application but
are deliberately decoupled: the Gateway depends on Core services (to read agents,
persist messages, retrieve knowledge) but keeps only ephemeral, in-memory session state
of its own, so it can be restarted or scaled without data loss.

```
        ┌─────────────────────────────┐
        │   Desktop (gabriel-desktop) │  Next.js web/desktop client
        └──────────────┬──────────────┘
                       │ HTTPS / SSE
        ┌──────────────▼──────────────┐
        │        API (FastAPI)        │  routers + middleware
        │  ┌────────────┬───────────┐ │
        │  │  Gateway   │   Core    │ │
        │  │ (stateless │ (durable  │ │
        │  │  runtime)  │  domain)  │ │
        │  └─────┬──────┴─────┬─────┘ │
        └────────┼────────────┼───────┘
                 │            │
        ┌────────▼───┐  ┌─────▼─────────────┐
        │   Ollama   │  │ PostgreSQL +      │
        │ (LLM/embed)│  │ pgvector          │
        └────────────┘  └───────────────────┘
```

---

## 2. Universal Resources & GRNs

Every meaningful entity in Gabriel — users, organizations, agents, conversations,
messages, documents, knowledge sources, memory layers, notifications, policies — is a
**Universal Resource**. Each carries a **Global Resource Name (GRN)** of the form:

```
grn:{org}:{resource_type}/{id}:{version}
```

GRNs make identity, tenancy, and type explicit in a single string. The org segment
enforces **multi-tenancy** (a resource always belongs to exactly one organization); the
type segment drives resource-type registration and authorization; the version segment
supports optimistic concurrency and lifecycle tracking.

- Resource types are enumerated in `gabriel/resource/models.py` (`ResourceType`) and
  registered at startup in `gabriel/resource/bootstrap.py`.
- GRNs are generated and parsed centrally (`GRN.generate(org_id=, resource_type=)`), so
  every slice produces consistent identifiers.
- A resource's **metadata** is distinct from its **content**: for documents, metadata
  (a Universal Resource) lives in the database, while the raw file bytes live in a
  content store on disk. Derived data such as document **chunks** are intentionally *not*
  Universal Resources — they are rebuilt on demand (see ADR-0015).

This uniform model is the foundation that ADR-0009 (GRN factory) and ADR-0001
(principal/resource mirroring) established, and every later phase builds on it.

---

## 3. PEEL authorization

**PEEL** (Policy Enforcement & Evaluation Layer) is Gabriel's centralized authorization
system. Rather than scattering permission checks through handlers, PEEL evaluates every
request against declarative policies.

- **Capabilities** (`gabriel/policy/capabilities.py`) map API domains and verbs to
  named capabilities such as `document:read`, `knowledge:search`, `agent:update`.
- The **authorization middleware** (`gabriel/api/middleware/authorization.py`) derives
  the required capability from the request's URL prefix and HTTP method (e.g. a
  `POST /knowledge/search` maps to the `knowledge` domain with a `search` verb), then
  asks the PEEL engine whether the authenticated principal may proceed.
- **Tenant isolation** is enforced on top of capability checks: a principal may only act
  on resources whose GRN belongs to its own organization. Cross-org access returns
  `403`.

PEEL wiring and its integration with the command pipeline are described in ADR-0010 and
extended for later domains in ADR-0012 (auth/membership) and ADR-0015 (document &
knowledge capabilities).

---

## 4. Event Store

Gabriel is **event-sourced** for its domain mutations. Instead of only mutating rows,
state-changing commands emit events (`resource_created`, `resource_updated`,
`resource_deleted`, and domain-specific variants) that are appended to an event store.

- The event store (`gabriel/events/`) is the write-side source of truth.
- **Projections** consume events to build read models — for example a resource read
  model (for fast list/get queries) and an audit projection. On startup, if the read
  model is empty but events exist, the dispatcher **replays** events to rebuild
  projections.
- Some domains (notifications) subscribe to events to react to system activity — e.g.
  `NotificationService.create_from_event` turns a domain event into a user notification.
- The event store persists to PostgreSQL; if the database is unreachable at startup the
  application falls back to a local SQLite store so development can continue.

This gives Gabriel a durable audit trail, the ability to rebuild derived state, and a
clean separation between the command (write) and query (read) sides.

---

## 5. Vertical slice structure

Business capabilities are implemented as **vertical slices**. Each slice owns its full
stack and follows the same layered pattern:

```
Model (Pydantic)  →  ORM (SQLAlchemy)  →  Mapper  →  Repository  →  Service  →  Router
```

- **Model** — Pydantic schemas for validation and serialization.
- **ORM** — SQLAlchemy table mapping.
- **Mapper** — converts between ORM rows and read models (e.g. IDs → GRNs).
- **Repository** — data access; encapsulates queries and soft-delete rules.
- **Service** — business logic, event emission, cross-slice orchestration.
- **Router** — FastAPI endpoints, thin, delegating to the service.

Current slices include: `conversation` (conversations + messages), `agent`,
`notification`, `memory` (memory layers), `document`, and `knowledge`. This uniformity
(established for the core business domains in ADR-0013) makes each slice independently
understandable and testable, and keeps new features from leaking across boundaries.

---

## 6. Provider abstraction pattern

Gabriel avoids hard-coupling to any single AI vendor by using a **registry + protocol**
pattern in two places, both mirroring each other:

- **LLM providers** (`gabriel/gateway/providers/`): an `LLMProvider` protocol defines a
  provider-neutral wire format (`ChatMessage`, `StreamChunk`, `ToolCallRequest`,
  `TokenUsage`, …) and operations (`chat_completion`, `stream_chat_completion`,
  `list_models`, `health_check`). A `ProviderRegistry` registers implementations by
  name with a configurable default. `OllamaProvider` is the default implementation; its
  HTTP transport is injectable so tests use `httpx.MockTransport` instead of a live
  daemon. (ADR-0014.)
- **Embedding providers** (`gabriel/knowledge/embeddings.py`): an `EmbeddingProvider`
  protocol and an `EmbeddingProviderRegistry` follow exactly the same shape.
  `OllamaEmbeddingProvider` (model `nomic-embed-text`, 768 dimensions) is the default,
  and providers are hot-swappable at runtime. (ADR-0015.)

Both registries share these properties: named registration with a default, runtime
resolution, and **graceful degradation** — a provider connection error surfaces as a
structured error (or, for RAG, a keyword-search fallback) rather than a crash.

### How the Gateway assembles a chat turn

1. Resolve the agent's runtime config (system prompt, model, `knowledge_sources`).
2. Persist the user message (Core).
3. If the agent has knowledge sources, the `KnowledgeRetriever` embeds the query,
   performs a cosine similarity search over document chunks, and returns
   `ContextBlock`s (falling back to keyword search if embedding is unavailable).
4. The `PromptAssembler` composes the final prompt: system prompt + retrieved context
   blocks + a windowed conversation history + the current user turn.
5. The resolved `LLMProvider` streams the completion; tokens are emitted as SSE events,
   along with a `context` event describing which chunks grounded the reply.
6. The assistant message is persisted (Core), and ephemeral session/token accounting is
   updated in the Gateway's in-memory `SessionManager`.

This keeps RAG, prompt engineering, and vendor choice as swappable strategies layered
over a stable, event-sourced core.

---

## 7. Storage summary

| Data | Where it lives |
|------|----------------|
| Universal Resource metadata, events, read models | PostgreSQL (SQLite fallback in dev) |
| Document chunk vectors | PostgreSQL `document_chunks.embedding vector(768)` + HNSW cosine index (JSON + in-process cosine on SQLite) |
| Raw uploaded file bytes | Local filesystem content store (`GABRIEL_CONTENT_ROOT`), content-addressed by SHA-256 |
| Chat sessions & token counters | In-memory in the Gateway (ephemeral, TTL-evicted) |

---

## 8. Architecture Decision Records

The design evolved across phases, each documented in an ADR:

| ADR | Title | Phase focus |
|-----|-------|-------------|
| [0012](adr/0012-password-auth-and-org-membership.md) | Password Authentication, Refresh Tokens & Organization Membership | Identity, multi-tenancy, PEEL foundations |
| [0013](adr/0013-core-business-logic.md) | Core Business Logic — Conversations, Messages, Agent Management, Notifications, Memory Layers | Vertical-slice domain services |
| [0014](adr/0014-gateway-ai-runtime.md) | Gateway AI Runtime — Providers, Streaming Chat, Tools, Sessions | Stateless LLM gateway & provider abstraction |
| [0015](adr/0015-document-knowledge-rag.md) | Document & Knowledge — Uploads, Chunking, pgvector Embeddings, and RAG | Document ingestion, vector storage, RAG |

Earlier ADRs (0001, 0009, 0010, 0011) cover the original Universal Resource, GRN
factory, PEEL wiring, and agent-specification foundations that these phases build upon.
