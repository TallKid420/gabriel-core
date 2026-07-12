# Agent Specification System

**Status:** Implemented (Phase 4 — Agent Migration)
**Module:** `gabriel.agent`

This document describes the declarative agent-specification system in
`gabriel-core`: the template library that mirrors the legacy Gabriel agent
types, the GRN tool-binding format, the capability and memory models,
persistence, and how `gabriel-desktop` wires itself to this system.

---

## 1. Overview

In the legacy Gabriel codebase, agents were **Python classes** (`ChatAgent`,
and the experimental `EngineerAgent` / `ResearcherAgent` / `DaemonAgent` /
`ServerAgent`) configured through `agents.yaml` and instantiated by a factory
and registry. Behaviour, tool access, and memory usage were entangled in code.

In the new architecture an agent is a **declarative
[`AgentSpecification`](../src/gabriel/agent/specification.py)** — a data object
describing *what* an agent is (capabilities, tools, memory, triggers, runtime
config) without hard-coding *how* it runs. A runtime (e.g. LangGraph) executes
a spec; the spec is portable, serialisable, and reviewable.

```
Legacy                          New (gabriel-core)
------                          ------------------
class ChatAgent(BaseAgent)  ->  AgentSpecification(template="chat", ...)
agents.yaml                 ->  AgentTemplate library + AgentSpecificationStore
factory + registry          ->  build_specification() + runtime selection
hard-coded tool lists       ->  GRN tool bindings (grn:<org>:tool/<name>:<ver>)
```

## 2. Template library

The template library lives in
[`gabriel/agent/templates.py`](../src/gabriel/agent/templates.py) and captures
every legacy agent type as a reusable `AgentTemplate`.

| Key          | Legacy class      | Purpose                                             | Default model  |
|--------------|-------------------|-----------------------------------------------------|----------------|
| `chat`       | `ChatAgent`       | Interactive conversational assistant                | `gpt-oss:120b` |
| `engineer`   | `EngineerAgent`   | Coding / file-editing agent with tool use           | `gpt-oss:120b` |
| `researcher` | `ResearcherAgent` | Web research + summarisation, scheduled runs        | `gpt-oss:120b` |
| `daemon`     | `DaemonAgent`     | Background worker driven by events/schedules        | `gpt-oss:20b`  |
| `server`     | `ServerAgent`     | Headless request/response service agent             | `gpt-oss:20b`  |

Each template records its provenance in `metadata`
(`template`, `legacy_class`, `migrated_from`) so a materialised spec can always
be traced back to the legacy type it replaces.

### API

```python
from gabriel.agent import (
    list_templates,        # -> ["chat", "engineer", "researcher", "daemon", "server"]
    get_template,          # -> AgentTemplate
    build_specification,   # -> AgentSpecification (template + overrides)
    template_vocabulary,   # -> allowed runtimes/tools/capabilities/memory/models
)

spec = build_specification("chat", name="support-bot", model="gpt-oss:120b")
```

`build_specification(key, **overrides)` supports overrides for `name`, `model`,
`provider`, `system_prompt`, `metadata`, and `extra_tools` (appended as GRN
bindings).

## 3. Capabilities

[`gabriel/agent/capabilities.py`](../src/gabriel/agent/capabilities.py) defines
the `AgentCapability` enum — the declarative capability vocabulary:

`CHAT`, `STREAM`, `MEMORY_READ`, `MEMORY_WRITE`, `MEMORY_PROMOTE`,
`TOOL_INVOKE`, `FILE_READ`, `FILE_WRITE`, `INTEGRATION_READ`,
`INTEGRATION_WRITE`, `EVENT_SUBSCRIBE`, `SCHEDULE`.

Agent-level capabilities are mapped to **runtime** capabilities through
`AGENT_TO_RUNTIME_CAPABILITY` / `to_runtime_capabilities()`, so the runtime
layer only sees the capabilities it needs to enforce. `AgentSpecification`
stores capabilities as strings (their enum `.value`), keeping the spec JSON
human-readable and backward-compatible with the pre-existing free-form format.

The three capabilities called out by the migration brief — **CHAT**,
**MEMORY_READ**, **MEMORY_WRITE** — are present on the `chat` template.

## 4. Tool bindings (GRN)

Tools are referenced with **Gabriel Resource Names (GRNs)** rather than bare
slugs, so a spec is explicit about *which* org-scoped tool + version it may
call. The binding helpers live in
[`gabriel/agent/grn_bindings.py`](../src/gabriel/agent/grn_bindings.py).

```
grn:<org>:tool/<name>:<version>
     │       │         │
     │       │         └── version (integer) or "*" wildcard
     │       └──────────── tool slug (e.g. get_time)
     └──────────────────── org id, or "*" wildcard
```

Templates ship **wildcard** bindings (`grn:*:tool/get_time:*`) that are
portable across orgs. At instantiation time the desktop/gateway layer resolves
them to concrete org-scoped GRNs:

```python
spec.resolved_tools(org_id="acme", version=1)
# -> ["grn:acme:tool/get_time:1", ...]
```

Helpers: `tool_grn()`, `is_tool_grn()`, `parse_tool_grn()`, `tool_name()`,
`resolve_tools()`, and the `ToolBinding` dataclass.

> **Note:** wildcard GRNs are intentionally *not* parsed by
> `gabriel.resource.grn.GRN`, which requires an integer version. The
> `grn_bindings` module provides its own lightweight parser so specs can carry
> unresolved, portable bindings.

`AgentSpecification.tool_names()` returns the bare slugs (used for validation
against the tool registry vocabulary), while the stored `tools` list keeps the
GRN bindings.

## 5. Memory configuration

Specs declare which memory layers they read from and write to. Layers come
from `gabriel.memory.models.MemoryLayer`
(`WORKING`, `SHORT_TERM`, `LONG_TERM`, `EPISODIC`, `SEMANTIC`, `PROCEDURAL`,
`ARCHIVAL`, `EXTERNAL`).

* `AgentSpecification.memory_layers` — flat list of layers the agent uses.
* `AgentSpecification.memory` — optional `MemoryRequirements`
  (`read_layers`, `write_layers`, `retention`) for finer control.

The `chat` template, for example, reads `working / short_term / long_term`
and writes `working / short_term` with `session` retention.

## 6. Triggers

Each template declares trigger bindings (`event_type` + optional `filter`)
describing what wakes the agent — e.g. `UserMessageReceived` and
`api:POST:/chat/send` for chat, schedule events for the researcher/daemon.
`AgentSpecification.normalized_triggers()` returns them as structured objects.

## 7. Runtime configuration & selection

`AgentSpecification.runtime` names the runtime (default `langgraph`), and the
optional `runtime_config` (`RuntimeConfiguration`) carries `timeout_seconds`,
`max_iterations`, `temperature`, and `max_tokens`.

At execution time the `AgentExecutor` selects a runtime via
`request.metadata.get("runtime", request.agent.specification.runtime)` — i.e.
**the spec drives runtime selection**. This is proven end-to-end in
`tests/agent/test_spec_execution.py`, which swaps the runtime to a `MockRuntime`
purely through the spec.

## 8. Persistence

[`gabriel/agent/store.py`](../src/gabriel/agent/store.py) provides the
`AgentSpecificationStore` — a file-backed store (JSON, optional YAML) that is
the shared **authoring format** (the analogue of the legacy `agents.yaml`).

```python
from gabriel.agent import AgentSpecificationStore

store = AgentSpecificationStore(".gabriel/agent-specs")
path = store.save(spec)            # -> .gabriel/agent-specs/<name>.json
spec = store.load("support-bot")
names = store.list()
store.delete("support-bot")
```

Methods: `save`, `save_many`, `load`, `load_all`, `list`, `exists`, `delete`,
`path_for`. Missing specs raise `SpecificationNotFoundError`.

> There is *also* a database-backed persistence path (`AgentService` /
> `AgentRepository` / ORM) already present in `gabriel-core` for runtime
> storage. The file store is complementary: it is for version-controllable,
> reviewable spec **authoring** and seeding.

### Seeding

`scripts/seed_agent_specs.py` materialises the whole template library to a
directory (the migration analogue of shipping `agents.yaml`):

```bash
PYTHONPATH=src python scripts/seed_agent_specs.py --out examples/agent-specs
# or YAML:
PYTHONPATH=src python scripts/seed_agent_specs.py --out examples/agent-specs --format yaml
```

Sample output lives in [`examples/agent-specs/`](../examples/agent-specs/).

## 9. Desktop ↔ Core wiring (over HTTP)

`gabriel-desktop` does **not** re-implement agent modelling **and does not
install or import `gabriel-core`**. The two are wired together purely over
**HTTP**: gabriel-core owns all agent-spec logic and exposes it; the desktop
gateway (BFF) is a thin HTTP client that forwards requests and relays JSON.

**Core side (owns the logic + endpoints):**
* `src/gabriel/api/services/agent_specs.py` — `AgentSpecService` (templates,
  instantiate + validate, GRN resolution, save/load/list/delete).
* `src/gabriel/api/routers/agent_specs.py` — FastAPI router mounted at
  `/api/v1/agent-specs`, registered in `src/gabriel/api/app.py`. These routes
  are allowlisted as public in the authorization middleware (config/authoring
  endpoints, no principal-scoped data).

**Desktop side (HTTP client only):**
* `apps/gateway/src/gabriel_gateway/core_specs.py` — `CoreSpecClient`, an
  `httpx` client that calls gabriel-core. **No `gabriel.*` imports.**
* `apps/gateway/src/gabriel_gateway/main.py` — the browser-facing gateway API,
  which forwards to `CoreSpecClient`.

```
Browser ──HTTP──▶ Gateway (FastAPI BFF) ──HTTP──▶ gabriel-core
                  CoreSpecClient (httpx)          /api/v1/agent-specs
                  no gabriel import               AgentSpecService (all logic)
```

Core endpoints (mounted under `/api/v1`):

| Method | Path                                | Purpose                                |
|--------|-------------------------------------|----------------------------------------|
| GET    | `/api/v1/agent-specs/templates`     | list migrated template descriptors     |
| POST   | `/api/v1/agent-specs/instantiate`   | build a spec from template + overrides |
| GET    | `/api/v1/agent-specs`               | list persisted spec names              |
| POST   | `/api/v1/agent-specs`               | build + persist a spec                 |
| GET    | `/api/v1/agent-specs/{name}`        | load a persisted spec                  |
| DELETE | `/api/v1/agent-specs/{name}`        | delete a persisted spec                |

The gateway re-exposes these to the browser under `/agent-specs/*` (same shape).

**Configuration:**
* Core: `GABRIEL_AGENT_SPECS_DIR` (spec store), `GABRIEL_DEFAULT_ORG_ID` (GRN org).
* Gateway: `GABRIEL_GATEWAY_CORE_BASE_URL` (defaults to `http://localhost:8000`).

**Run both (two independent services):**

```bash
# terminal 1 — gabriel-core
cd gabriel-core
GABRIEL_AGENT_SPECS_DIR=.gabriel/agent-specs uvicorn gabriel.api.app:app --port 8000

# terminal 2 — gabriel-desktop gateway
cd gabriel-desktop/apps/gateway
GABRIEL_GATEWAY_CORE_BASE_URL=http://localhost:8000 \
  uvicorn gabriel_gateway.main:app --port 8100 --app-dir src
```

## 10. Validation & tests

* `gabriel-core`: `tests/agent/` (GRN bindings, templates, spec store,
  spec-driven execution) — run with `PYTHONPATH=src pytest tests/agent`.
* `gabriel-core`: `tests/api/test_agent_specs_api.py` (the HTTP endpoints the
  gateway consumes).
* `gabriel-desktop`: `apps/gateway/tests/` (the `CoreSpecClient` HTTP seam +
  the gateway's FastAPI API). Tests drive gabriel-core's ASGI app through an
  in-process HTTP transport, so the two-hop path is exercised without sockets —
  run with `PYTHONPATH=src pytest tests/`.

All template specs are validated against the template vocabulary via
`AgentValidator` (checking runtimes, tool names, capabilities, memory layers,
and models).

## 11. File map

```
gabriel-core/
  src/gabriel/agent/
    capabilities.py   AgentCapability enum + runtime mapping
    grn_bindings.py   GRN tool-binding format + helpers
    specification.py  AgentSpecification (+ tool_names/resolved_tools/…)
    templates.py      AgentTemplate library (chat/engineer/researcher/daemon/server)
    store.py          AgentSpecificationStore (file persistence)
  src/gabriel/api/
    services/agent_specs.py  AgentSpecService (all agent-spec logic)
    routers/agent_specs.py   HTTP router (/api/v1/agent-specs)
    app.py                   registers the router
  scripts/seed_agent_specs.py    materialise templates to disk
  examples/agent-specs/          sample seeded specs
  tests/agent/                   unit + integration tests
  tests/api/test_agent_specs_api.py  HTTP endpoint tests

gabriel-desktop/                 (no gabriel-core dependency)
  apps/gateway/src/gabriel_gateway/
    settings.py       gateway settings (core_base_url, …)
    core_specs.py     CoreSpecClient — httpx client to gabriel-core
    main.py           FastAPI app forwarding to core over HTTP
  apps/gateway/tests/            HTTP seam + gateway API tests
```
