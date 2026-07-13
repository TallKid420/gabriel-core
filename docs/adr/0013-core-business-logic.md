# ADR-013: Core Business Logic — Conversations, Messages, Agent Management, Notifications, Memory Layers

- **Status:** Accepted
- **Date:** 2026-07-12
- **Phase:** 2 — Core Business Logic
- **Builds on:** ADR-009 (GRN Factory Integration), ADR-011 (Agent Specification
  Migration), ADR-012 (Password Auth & Org Membership), ADR-017 (Transactional
  Outbox — events in the same transaction as the write)

## Context

Phase 1 delivered the backend foundations: Universal Resources with GRNs,
org-scoped tenancy, password authentication, user management, and the
`/api/v1` router layout. Phase 2 adds the product's core domain objects:
conversations and their messages, operator-facing agent management,
notifications derived from domain events, and governed memory layer entries.

The pre-existing `/agents` and `/notifications` routers were placeholders
backed by in-memory gateway state; conversations and governed memory metadata
did not exist at all.

## Decision

Each new domain follows the established **vertical slice** architecture:

```
Model (pydantic, frozen) → ORM (SQLAlchemy) → Mapper → Repository → Service → Router
```

All new entities are **Universal Resources**: GRN-addressed, org-scoped,
versioned, audited (`created_by`/`updated_by`), created through the
`ResourceFactory` (ADR-009), and every mutation appends a domain event in the
same transaction (ADR-017).

### 1. Conversations (`gabriel.conversation`)

- Table `conversations`: `title`, `status` (`active` | `archived`),
  `participants` (JSON list of principal/user identifiers), optional
  `agent_grn`.
- CRUD + paginated listing (`limit`/`offset`, returns `total`), optional
  status filter. Deletion is a **soft delete** (`state = deleted`) — the
  thread is an audit artifact; reads and listings hide deleted rows.
- Router: `GET/POST /api/v1/conversations`,
  `GET/PATCH/DELETE /api/v1/conversations/{grn}`.

### 2. Messages (`gabriel.conversation.message_*`)

- Table `messages`: `conversation_grn` (indexed), `role`
  (`user` | `assistant` | `system` | `tool`), `content`, `metadata` JSON,
  token accounting (`prompt_tokens`, `completion_tokens`, `total_tokens` —
  the total defaults to the sum when omitted), `model` used, timestamps.
- Append-only: create + paginated chronological listing per conversation.
  Appending to an archived or deleted conversation raises
  `ConversationClosedError` → HTTP 409.
- Each append emits a `message_created` event.
- Router (nested): `GET/POST /api/v1/conversations/{grn}/messages` — declared
  before the bare `/{grn:path}` routes because the greedy path converter
  would otherwise swallow them.

### 3. Agent Management (`gabriel.agent.management`)

Operators think in terms of `name`, `description`, `system_prompt`,
`model_config` (provider/model/temperature/max_tokens), `allowed_tools`,
`knowledge_sources`, and `status` (`active` | `inactive` | `draft`).
Internally these map onto the persisted `AgentSpecification` (ADR-011) so the
runtime/deployment machinery keeps working unchanged:

| management field   | storage                                            |
|--------------------|----------------------------------------------------|
| model_config       | spec `provider`/`model` + runtime config `temperature`/`max_tokens` |
| allowed_tools      | spec `tools`                                       |
| knowledge_sources  | spec `knowledge_sources` (new field)               |
| status `active`    | `ResourceState.ACTIVE`, `enabled=True`             |
| status `inactive`  | `ResourceState.SUSPENDED`, `enabled=False`         |
| status `draft`     | `ResourceState.DRAFT`, `enabled=False`             |

`AgentManagementService` provides DB-backed CRUD + paginated listing; the
`/api/v1/agents` router now uses it (replacing the in-memory gateway CRUD),
while `/execute`, `/enable`, `/disable` keep flowing through the gateway
command path. (pydantic v2 reserves the `model_config` attribute name, so the
API request models expose the field through an alias — the wire format is
unchanged.)

### 4. Notifications (`gabriel.notification`)

- Table `notifications`: `recipient` (user GRN, falling back to principal id
  for service accounts), `type`, `title`, `body`, `read`/`read_at`,
  `source_event_id`, `metadata` JSON.
- `NotificationService.create_from_event(event, recipient)` is the primary
  write path: the notification's type mirrors the event type, a template map
  derives human titles, and `causation_id` chains back to the source event.
  Notification writes emit `notification_*` events, which are never
  themselves turned into notifications (no recursive fan-out).
- `mark_read` is idempotent (no double version bump); `mark_all_read` is a
  single UPDATE.
- Router: `GET /api/v1/notifications` (with `unread_count`),
  `POST /api/v1/notifications/read-all`,
  `POST /api/v1/notifications/{grn}/read` (plus a legacy `PATCH /{grn}`
  alias). There is deliberately **no public creation endpoint**.

### 5. Memory Layers (`gabriel.memory.layer_*`)

- Table `memory_layer_entries`: `key`, `value` (JSON), `scope`
  (`global` | `org` | `user` | `agent` | `conversation`), `subject_grn`
  (which user/agent/conversation the entry belongs to), `tags` (JSON list),
  `expires_at`.
- Keys are unique per `(org, scope, subject)` namespace
  (`uq_memory_layer_entries_namespace_key`); duplicates raise
  `DuplicateResourceError` → HTTP 409. Expired entries behave as if they do
  not exist (filtered on every read) and free their namespace slot.
- Deletion is a **hard delete** — memory purges must actually remove data —
  but the `resource_deleted` event survives in the event store.
- Distinct from `memory_entries` (`gabriel.memory.orm`), which is the
  runtime MGE/pgvector working memory; layer entries are governed resource
  metadata. Router `GET/POST /api/v1/memory/layers` +
  `GET/PATCH/DELETE /api/v1/memory/layers/{grn}` is registered **before** the
  legacy `/memory` gateway router so the more specific prefix wins.

### Cross-cutting wiring

- `ResourceType` enum gains `CONVERSATION`, `MESSAGE`, `NOTIFICATION`
  (`MEMORY` already existed); `register_core_resource_types()` registers
  `conversation`, `message`, `notification`, `memory_layer_entry`.
- PEEL: `conversation:*`, `message:*`, `notification:*`, `memory:*` actions
  mapped in `ACTION_CAPABILITY_MAP` (reads → `READ_RESOURCE`, writes →
  `WRITE_RESOURCE`); the authorization middleware maps the `conversations`
  and `notifications` URL prefixes to their domains.
- Tenant isolation is enforced twice: org-scoped queries in every repository
  and a `_require_same_org` GRN check in every router (403 on cross-tenant
  GRNs), on top of the PEEL middleware.
- Migration `j0d4e6f8a2b3` (down_revision `i9c3d5e7f1a2`) creates the four
  tables with the standard resource column set, indexes for the hot listing
  paths, and the memory namespace unique constraint.

## Consequences

- Conversations, messages, agents, notifications, and memory layer entries
  are governed like every other resource: GRNs, org scoping, versioning,
  full event audit trail.
- The stale in-memory `/agents` CRUD and mock `/notifications` endpoints are
  gone; their API tests were rewritten against the DB-backed contracts.
- Messages are append-only by design; editing/deleting messages would require
  a new ADR (audit implications).
- Tag filtering on memory listings is applied post-query (JSON column); if it
  becomes hot, a join table or JSONB containment index is the upgrade path.
- Notification fan-out (which events notify whom) is a policy decision left
  to callers of `create_from_event`; a subscription/preferences model is
  future work.
