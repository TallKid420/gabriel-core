# ADR-011: Agent Specification Migration (Phase 4)

**Date:** 2026-07-08
**Status:** ✅ IMPLEMENTED
**Milestone:** Phase 4 — Agent Migration

## Context

Legacy Gabriel modelled agents as Python classes (`ChatAgent`, plus the
experimental `EngineerAgent` / `ResearcherAgent` / `DaemonAgent` /
`ServerAgent`), configured through `agents.yaml` and instantiated by a factory
+ registry. Behaviour, tool access, and memory usage were entangled in code,
which made agents hard to review, port, and persist independently of the
runtime.

The new architecture treats an agent as a **declarative specification** that a
runtime executes. Phase 4 migrates the legacy agent taxonomy into this model
and wires `gabriel-desktop` to consume it.

## Decision

1. **Template library.** Every legacy agent type is captured as an
   `AgentTemplate` (`gabriel/agent/templates.py`): `chat`, `engineer`,
   `researcher`, `daemon`, `server`. Each records provenance
   (`template`, `legacy_class`, `migrated_from`) in metadata.

2. **Capability vocabulary.** Introduce the `AgentCapability` enum
   (`gabriel/agent/capabilities.py`) including `CHAT`, `MEMORY_READ`,
   `MEMORY_WRITE`, `TOOL_INVOKE`, etc., with an explicit
   `AGENT_TO_RUNTIME_CAPABILITY` mapping to runtime capabilities. Specs store
   capability `.value` strings to stay backward-compatible and human-readable.

3. **GRN tool bindings.** Tools are referenced as
   `grn:<org>:tool/<name>:<version>` with `*` wildcards for portability
   (`gabriel/agent/grn_bindings.py`). A lightweight parser is used instead of
   `resource.grn.GRN` because the latter requires an integer version and cannot
   represent unresolved wildcards. Bindings are resolved to concrete org-scoped
   GRNs at instantiation time.

4. **Memory declarations.** Specs declare `memory_layers` and an optional
   `MemoryRequirements` (`read_layers`, `write_layers`, `retention`) over
   `memory.models.MemoryLayer`.

5. **File-based persistence.** `AgentSpecificationStore`
   (`gabriel/agent/store.py`) provides JSON/YAML save/load — the
   version-controllable authoring format replacing `agents.yaml`. This is
   complementary to the existing DB-backed `AgentService`/`AgentRepository`
   used for runtime storage.

6. **Spec-driven runtime selection.** The `AgentExecutor` selects a runtime
   from the spec (`request.agent.specification.runtime`), proven end-to-end in
   `tests/agent/test_spec_execution.py`.

7. **Desktop ↔ core wiring.** The desktop gateway (BFF) imports `gabriel.agent`
   through `CoreSpecService` and exposes it over HTTP. The gateway holds no
   agent business logic (consistent with the BFF ADR).

## Backward compatibility

`AgentSpecification` was extended additively (new optional fields:
`provider`, `runtime_config`, `memory`; new helper methods). Existing tests
that use free-form capability/tool/memory strings continue to pass; the full
`tests/agent` + `tests/runtime` suite (127 tests) is green.

## Consequences

* Agents are now declarative, portable, reviewable, and serialisable.
* Tool access is explicit and org-scoped via GRNs.
* The desktop app consumes a single source of truth for agent modelling.
* Adding a new agent type is a data change (a new template) rather than a new
  class hierarchy.

## References

* `docs/agent-specification-system.md` — full system documentation.
* `gabriel/agent/{templates,capabilities,grn_bindings,store,specification}.py`
* `scripts/seed_agent_specs.py`, `examples/agent-specs/`
* `gabriel-desktop/apps/gateway/src/gabriel_gateway/{core_specs,main}.py`
