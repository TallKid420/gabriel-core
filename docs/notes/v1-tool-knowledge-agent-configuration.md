# V1 — Tool, Knowledge & Agent Configuration Resources

Implementation notes for the V1 resource-model milestone: Tool as a Universal
Resource, knowledge-source abstraction, document collections, and
agent-configuration-driven chat runtime.

## Gap analysis (what already existed)

The codebase was further along than the planning documents assumed. Before
this change:

- **Tool** was already a Universal Resource (`gabriel/tool/`) with name,
  description, category, input/output schemas, safety level, required
  capabilities and runtime binding — full model → ORM → mapper → repository →
  service slice, registered in `resource/bootstrap.py` (ADR-009 / ADR-016).
  Missing: `execution_runtime`, `enabled`, `configuration`, and any HTTP API.
- **KnowledgeSource** existed (`gabriel/knowledge/`) as a Universal Resource
  grouping documents for RAG, with a full API under `/api/v1/knowledge`.
  Missing: a source *type* discriminator decoupling the abstraction from the
  vector store.
- **Document** existed (`gabriel/document/`) as a Universal Resource with a
  library service and `/api/v1/documents` API. No changes were needed there.
- **AgentSpecification** already carried `tools` and `knowledge_sources`.
  Missing: `disabled_tools` and `document_collections`.
- **ChatRuntimeService** (`gabriel/gateway/service.py`) already resolved
  provider/model/system-prompt/tools/knowledge from the agent specification —
  nothing was hardcoded. Missing: disabled-tool subtraction, org-level
  `Tool.enabled` governance, and document-collection grounding.

The work therefore extends existing slices instead of adding parallel ones.

## Changes

### 1. Tool resource (`gabriel/tool/`)

- `ExecutionRuntime` enum: `local` / `enterprise` / `cloud` / `edge`.
  **Declaration only in V1** — no execution engine consumes it yet; declaring
  it now avoids a later schema migration when runtime routing lands.
- New fields on `Tool`: `execution_runtime` (default `local`), `enabled`
  (default `True`), `configuration` (JSON dict), all round-tripped through
  ORM, mappers, repository and service; `Tool.public_view()` added.
- `ToolService.create_tool` / `update_tool` accept the new fields;
  `update_tool` now coerces enum inputs explicitly because
  `model_copy(update=...)` bypasses pydantic validation.
- `runtime_binding` is now optional (default `""`) — tools without a runtime
  binding are legal (registry entries for remote runtimes).

### 2. Knowledge sources (`gabriel/knowledge/`)

- `KnowledgeSourceType` enum: `vector_collection` (default),
  `document_collection`, `external`. The type is resolved inside the
  knowledge module only — agents and the chat runtime reference sources by
  GRN and never see storage details (no vector-DB coupling).
- `source_type` persisted, filterable in `list_sources`, exposed in
  `public_view()` and the API.

### 3. Document collections

**Design decision:** a document collection *is* a `KnowledgeSource` with
`source_type=document_collection`, not a new resource type. Both group
documents for agent grounding; duplicating the slice would have created a
second attach/detach/count/retrieval pipeline for the same behavior. External
knowledge bases later become `source_type=external` the same way.

### 4. Agent configuration (`gabriel/agent/`)

- `AgentSpecification` gains `disabled_tools` and `document_collections`.
- New helpers: `disabled_tool_names()`, `effective_tool_names()` (declared
  minus disabled — deny wins, mirroring PEEL semantics, ADR-008) and
  `grounding_source_grns()` (ordered dedupe of knowledge sources + document
  collections).
- `AgentManagementService.create_agent` / `update_agent` and the
  `/api/v1/agents` API accept and expose both new fields.

### 5. Chat runtime (`gabriel/gateway/service.py`)

Tool exposure and grounding come entirely from the agent configuration:

1. start from the agent's declared tools (or every registered runtime tool
   when the agent declares none);
2. drop the agent's `disabled_tools`;
3. drop any Tool resource the org disabled (`Tool.enabled = false`).

`allowed_tools = None` (unrestricted) is preserved only when the agent
declares nothing and nothing is disabled — prior behavior is unchanged for
existing agents. Org-level tool lookup degrades to an empty set on failure
(logged) so tool governance can never break a chat turn, matching the
retrieval resilience contract. RAG grounding now unions the agent's knowledge
sources and document collections.

### 6. API

- New `/api/v1/tools` router: create / list (filter by `category`, `enabled`,
  `execution_runtime`) / get / patch (incl. enable-disable toggle) / delete.
  Same conventions as the knowledge router: org-scoped GRNs, `public_view()`
  responses, 422 on unknown enum values, 403 cross-tenant, 404 missing,
  409 duplicate.
- `/api/v1/knowledge/sources` accepts `source_type` on create and as a list
  filter.

### 7. Migration

`alembic/versions/l3a7b9c1d5e6_add_tool_runtime_fields_and_source_type.py`
(revises `k1e5f7a9b3c4`): adds `tools.execution_runtime`, `tools.enabled`,
`tools.configuration`, `knowledge_sources.source_type` (+ index), all with
server defaults so existing rows need no backfill. Upgrade and downgrade
verified against SQLite.

## Architecture cleanup done along the way

- **`_require_same_org` duplication**: the same tenancy guard was copy-pasted
  in 8 routers (with drifting formatting). Extracted to
  `gabriel/api/tenancy.py::require_same_org`; all routers now import it.
- **Tracked runtime database**: `.gabriel/gateway_events.db` (the SQLite
  fallback store) was committed to git, so schema changes broke API tests
  against the stale binary. Removed from version control and added
  `.gabriel/` to `.gitignore`; tests recreate it from `Base.metadata`.
- **Stale tool tests**: `tests/tool/test_persistence.py` predated the
  `ToolCategory`/`SafetyLevel` enums (used `retrieval`, `nlp`, safety `3`)
  and required `runtime_binding`; both tests failed on `main`. Fixed to use
  valid enum values — the suite now covers the enum path.

## ADR compliance

- **ADR-005 (frozen resource models)**: no frozen base models modified; new
  fields are additive with defaults on domain subclasses.
- **ADR-008 (PEEL, deny wins)**: tool resolution applies deny-wins semantics;
  capability enforcement is unchanged.
- **ADR-009 / ADR-016 (Universal Resource Model / Tool as Resource)**: tools,
  knowledge sources and document collections remain GRN-addressed, org-scoped,
  versioned resources with metadata/labels.
- **ADR-011 (module boundaries)**: agent/gateway modules never import vector
  or storage internals; knowledge type resolution stays inside
  `gabriel/knowledge/`.

## Dependencies discovered for the roadmap

- Runtime *routing* on `execution_runtime` needs a dispatcher abstraction in
  the gateway before Enterprise/Cloud/Edge runtimes can be wired (V1 field is
  declarative only).
- Tool `configuration` is stored but not yet injected into tool execution —
  the runtime tool registry (`gateway/tools.py`) executes built-ins without
  per-org configuration. Wiring configuration into `RuntimeTool.run` is a
  natural follow-up.
- `source_type=external` is a stub: an external knowledge source needs a
  connector interface in `gabriel/knowledge/` (retrieval currently assumes
  locally stored chunks).

## Test results

`python -m pytest tests/` — **576 passed, 16 failed**; all 16 failures
pre-exist on `main` (auth-production, events, memory, PEEL enforcement,
resources read-model, streaming, document ingestion) and are untouched by
this change. `main` had 18 failures; this branch fixes the two
`tests/tool/test_persistence.py` failures and adds 17 new tests (tool fields,
spec config, runtime tool resolution, tools API, knowledge source types).
