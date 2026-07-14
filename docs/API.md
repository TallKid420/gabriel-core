# Gabriel — API Reference

A concise reference to the Gabriel HTTP API. All endpoints are served by the FastAPI
application (`gabriel.api.app:app`). Interactive, always-current documentation is
available at **`/docs`** (Swagger UI) and **`/openapi.json`** when the server is running.

## Conventions

- **Base path:** all application endpoints are versioned under `/api/v1`. Health checks
  live at the root (`/health`).
- **Authentication:** unless marked *Public*, every endpoint requires a bearer token:
  `Authorization: Bearer <access_token>`. Obtain one via `POST /api/v1/auth/register` or
  `POST /api/v1/auth/login`.
- **Authorization:** requests are additionally checked by the PEEL policy engine
  (capability + tenant isolation). Acting on a resource outside your organization
  returns `403`.
- **Identifiers:** resources are addressed by their GRN, e.g.
  `grn:acme:document/01J...:1`. In paths these are matched as `{grn:path}`.
- **Pagination:** list endpoints accept `limit`/`offset` (or `page`) query parameters and
  return `{ "items": [...], "total": <int> }`.

Legend: 🔓 = public (no auth), 🔒 = requires bearer token.

---

## Auth — `/api/v1/auth`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| POST | `/auth/register` | 🔓 | Self-service signup: creates an organization + owner user and returns an access token. |
| POST | `/auth/login` | 🔓 | Log in. `method: "password"` (credentials `{email, password, org_id}`) returns access + refresh tokens; `method: "dev"` for the dev provider. |
| POST | `/auth/refresh` | 🔓 | Rotate a refresh token (single-use) and mint a fresh access token. |
| POST | `/auth/logout` | 🔒 | Invalidate the current refresh token / session. |
| GET  | `/auth/me` | 🔒 | Current principal + organization details. |
| GET  | `/auth/jwks` | 🔓 | JSON Web Key Set for verifying issued JWTs. |
| GET  | `/auth/session` | 🔒 | Current session information. |
| GET  | `/auth/dev/principals` | 🔓 | Dev only: list seed principals available for dev login. |
| POST | `/auth/dev/login` | 🔓 | Dev only: log in as a seed principal by id. |

---

## Users — `/api/v1/users`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/users` | 🔒 | List users in the current organization. |
| POST | `/users` | 🔒 | Create a user. |
| GET  | `/users/me` | 🔒 | The authenticated user's own record. |
| POST | `/users/me/password` | 🔒 | Change the authenticated user's password. |
| GET  | `/users/{grn}` | 🔒 | Get a user by GRN. |
| PATCH | `/users/{grn}` | 🔒 | Update a user. |
| DELETE | `/users/{grn}` | 🔒 | Soft-delete a user. |

---

## Organizations — `/api/v1/organizations`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/organizations` | 🔒 | List organizations the principal can see. |
| GET  | `/organizations/{org_id}` | 🔒 | Get an organization. |
| PATCH | `/organizations/{org_id}` | 🔒 | Update an organization. |
| GET  | `/organizations/{org_id}/members` | 🔒 | List members. |
| POST | `/organizations/{org_id}/members` | 🔒 | Add a member. |
| PATCH | `/organizations/{org_id}/members/{principal_id}` | 🔒 | Update a member's role. |
| DELETE | `/organizations/{org_id}/members/{principal_id}` | 🔒 | Remove a member. |

---

## Agents — `/api/v1/agents`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/agents` | 🔒 | List agents in the organization (paginated). |
| POST | `/agents` | 🔒 | Create an agent (`name`, `system_prompt`, `model_config`, optional `knowledge_sources`). |
| GET  | `/agents/{grn}` | 🔒 | Get an agent. |
| PATCH | `/agents/{grn}` | 🔒 | Update an agent (incl. attaching `knowledge_sources` for RAG). |
| DELETE | `/agents/{grn}` | 🔒 | Soft-delete an agent. |
| POST | `/agents/{grn}/enable` | 🔒 | Enable an agent. |
| POST | `/agents/{grn}/disable` | 🔒 | Disable an agent. |
| POST | `/agents/{grn}/execute` | 🔒 | Execute the agent through the gateway runtime. |

### Agent specifications — `/api/v1/agent-specs`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/agent-specs/templates` | 🔒 | List available agent-spec templates. |
| POST | `/agent-specs/instantiate` | 🔒 | Instantiate an agent from a template. |
| GET  | `/agent-specs` | 🔒 | List stored agent specifications. |
| POST | `/agent-specs` | 🔒 | Create/store an agent specification. |
| GET  | `/agent-specs/{name}` | 🔒 | Get a specification by name. |
| DELETE | `/agent-specs/{name}` | 🔒 | Delete a specification. |

---

## Conversations & Messages — `/api/v1/conversations`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/conversations` | 🔒 | List conversations (paginated, filterable). |
| POST | `/conversations` | 🔒 | Create a conversation. |
| GET  | `/conversations/{grn}` | 🔒 | Get a conversation. |
| PATCH | `/conversations/{grn}` | 🔒 | Update / archive / unarchive a conversation. |
| DELETE | `/conversations/{grn}` | 🔒 | Soft-delete a conversation. |
| GET  | `/conversations/{grn}/messages` | 🔒 | List messages in a conversation. |
| POST | `/conversations/{grn}/messages` | 🔒 | Append a message to a conversation. |

---

## Gateway (AI runtime) — `/api/v1/gateway`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| POST | `/gateway/chat/stream` | 🔒 | Streamed chat turn (SSE): token deltas, an optional `context` event (RAG chunks), and a final done event. Body: `{conversation_grn, content, model?, provider?}`. |
| POST | `/gateway/chat` | 🔒 | Buffered chat turn; returns the full response. |
| GET  | `/gateway/providers` | 🔒 | List registered LLM providers and their health. |
| GET  | `/gateway/providers/{name}/models` | 🔒 | List models available from a provider. |
| GET  | `/gateway/tools` | 🔒 | List runtime tool specifications exposed to the LLM. |
| GET  | `/gateway/sessions` | 🔒 | List active chat sessions for the organization. |
| DELETE | `/gateway/sessions/{session_id}` | 🔒 | End an active session. |

There is also a lightweight `/api/v1/chat` router with `GET`/`POST /chat/conversations`
for simple conversation listing/creation.

---

## Documents — `/api/v1/documents`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| POST | `/documents` | 🔒 | Upload a document (multipart `file`; optional `source_uri`, `knowledge_source_grn`, `process`, `chunk_size`, `chunk_overlap`). Supported: PDF, TXT, MD, DOCX. Stored as a Universal Resource; chunked + embedded when `process=true` (default). |
| GET  | `/documents` | 🔒 | List documents (filter by `status`, `knowledge_source_grn`; paginated). |
| GET  | `/documents/{grn}` | 🔒 | Get document metadata. |
| GET  | `/documents/{grn}/content` | 🔒 | Get the extracted text content. |
| GET  | `/documents/{grn}/chunks` | 🔒 | List the document's chunks (paginated). |
| POST | `/documents/{grn}/process` | 🔒 | (Re)process: extract, chunk, embed. Query params `chunk_size`, `chunk_overlap`. |
| DELETE | `/documents/{grn}` | 🔒 | Soft-delete the document and purge its chunks. |

---

## Knowledge (sources & RAG search) — `/api/v1/knowledge`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| POST | `/knowledge/search` | 🔒 | Cosine similarity search over chunks (keyword fallback when embeddings are unavailable). Body: `{query, knowledge_source_grns?, document_grns?, limit?}`. |
| POST | `/knowledge/sources` | 🔒 | Create a knowledge source. |
| GET  | `/knowledge/sources` | 🔒 | List knowledge sources (paginated). |
| GET  | `/knowledge/sources/{grn}` | 🔒 | Get a knowledge source. |
| PATCH | `/knowledge/sources/{grn}` | 🔒 | Update a source (name, description, status). |
| DELETE | `/knowledge/sources/{grn}` | 🔒 | Soft-delete a source (detaches its documents). |
| GET  | `/knowledge/sources/{grn}/documents` | 🔒 | List documents attached to a source. |
| POST | `/knowledge/sources/{grn}/documents` | 🔒 | Attach a document (`{document_grn}`). |
| POST | `/knowledge/sources/{grn}/documents/detach` | 🔒 | Detach a document (`{document_grn}`). |

---

## Notifications — `/api/v1/notifications`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/notifications` | 🔒 | List notifications for the current user/org (filter by read status; paginated). |
| POST | `/notifications/read-all` | 🔒 | Mark all notifications as read. |
| POST | `/notifications/{grn}/read` | 🔒 | Mark one notification as read. |
| PATCH | `/notifications/{grn}` | 🔒 | Update a notification. |

> Notifications are created by the system in response to domain events, so there is no
> public create endpoint.

---

## Memory layers — `/api/v1/memory/layers`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/memory/layers` | 🔒 | List memory layers (filter by agent, user, type, scope; paginated). |
| POST | `/memory/layers` | 🔒 | Create a memory layer. |
| GET  | `/memory/layers/{grn}` | 🔒 | Get a memory layer. |
| PATCH | `/memory/layers/{grn}` | 🔒 | Update a memory layer. |
| DELETE | `/memory/layers/{grn}` | 🔒 | Soft-delete a memory layer. |

A legacy `/api/v1/memory` router (`GET`/`POST /memory`, `DELETE /memory/{memory_id}`)
remains for backward compatibility; the more specific `/memory/layers` routes take
precedence.

---

## Resources & Events (platform) — `/api/v1/resources`, `/api/v1/events`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET  | `/resources` | 🔒 | List Universal Resources via the materialized read model (excludes deleted by default). |
| POST | `/resources` | 🔒 | Create a resource through the command pipeline. |
| GET  | `/resources/{grn}` | 🔒 | Get a resource by GRN. |
| PATCH | `/resources/{grn}` | 🔒 | Update a resource. |
| DELETE | `/resources/{grn}` | 🔒 | Soft-delete a resource. |
| GET  | `/events` | 🔒 | List events from the event store. |
| GET  | `/events/stream` | 🔒 | Subscribe to the live event stream (SSE). |
| GET  | `/events/audit` | 🔒 | Query the audit projection. |
| GET  | `/events/{event_id}` | 🔒 | Get a single event. |

---

## Health — `/health`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| GET | `/health` | 🔓 | Overall health summary. |
| GET | `/health/live` | 🔓 | Liveness probe. |
| GET | `/health/ready` | 🔓 | Readiness probe. |
