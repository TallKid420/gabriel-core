# ADR-0010: PEEL Wiring and Core Document Ingestion

Status: Accepted
Layer: Core (Platform)

## Context

Two Core invariants were specified but not yet enforced end-to-end:

1. **PEEL must intercept every request and authorize it.** The `PEEL`,
   `PolicyEngine`, and a `peel` hook on the `Dispatcher` existed, but no PEEL
   instance was ever constructed or wired. Authorization was effectively a
   no-op: any authenticated principal could perform any action, and
   cross-tenant access was not blocked.
2. **A Document is a Resource, and uploading one must emit a ResourceCreated
   event.** No document subsystem existed in Core; the prototype's Docling
   normalization lived in the Application/daemon layer.

## Decision

### PEEL enforcement (defense in depth)

- `PEEL.authorize` now applies three ordered, fail-secure checks:
  1. **Multi-tenant isolation** — the resource GRN's `org_id` must match the
     execution context's organization. Structural; never overridable.
  2. **Policy evaluation** — when explicit policies are configured they are
     authoritative (explicit DENY wins; explicit ALLOW grants access).
  3. **Identity-based capability check** — when no policies are configured,
     the principal must hold the capability the action requires
     (`policy/capabilities.py` maps action verbs → `Capability`).
- A `PEEL` instance is constructed in `initialize_gateway_state` and wired into
  the `Dispatcher`, so **every state-changing command** is authorized before any
  event is recorded.
- The API middleware performs a **coarse PEEL pre-check** mapping HTTP
  method + path → action. This is the primary enforcement point for read (GET)
  requests, which do not dispatch commands.
- `UnauthorizedError` is mapped to HTTP **403**.

### Document ingestion (Core)

- New `gabriel.document` package: `Document` (a `Resource` subclass),
  `DocumentNormalizer` (migrated/cleaned from the prototype Docling pipeline,
  with a dependency-free plain-text/CSV/HTML fallback), and
  `DocumentIngestionService`.
- Ingestion dispatches a `create_resource` command (action `document:create`),
  so PEEL authorizes it and the Event Store records a `resource_created`
  (ResourceCreated) event transactionally.
- `docling`/`PyMuPDF`/`python-docx`/`beautifulsoup4` are **optional** extras;
  the Core path works without them.

## Layer assignment

- **Core**: PEEL wiring, capability map, `gabriel.document.*`, `/documents`
  gateway router (no chat/LLM/UI).
- **SDK**: would expose a thin `documents.upload(...)` client over `/documents`.
- **Desktop**: chat/RAG workflows consume ingested documents via the SDK.

## Consequences

- Cross-tenant access and missing-capability requests are now denied (403).
- Existing `test_peel.py` fixtures were updated to same-tenant GRNs to reflect
  the now-enforced structural isolation invariant.
- The Document resource is event-sourced like every other resource; no bespoke
  table is required for the ResourceCreated guarantee.
