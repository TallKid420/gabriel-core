# ADR-0015: Document & Knowledge — Uploads, Chunking, pgvector Embeddings, and RAG

- **Status:** Accepted
- **Date:** 2026-07-13
- **Phase:** 4 — Document & Knowledge

## Context

Phases 1–3 established Universal Resources (GRNs, events, PEEL policy), the memory
hierarchy, and the agent gateway with a `PromptAssembler` pipeline that composes
system prompts from ordered `ContextBlock`s. Agents can chat, but they cannot ground
their answers in organizational documents.

Phase 4 must let organizations upload documents, extract and chunk their text, embed
the chunks as vectors, group documents into knowledge sources, and automatically
retrieve relevant chunks into an agent's context during chat (RAG). The design must
follow the established vertical-slice pattern, remain org-scoped under PEEL, keep V1
simple, and avoid locking into a single embedding vendor.

## Decision

### 1. Two vertical slices: `document` and `knowledge`

- `gabriel/document/` owns the document lifecycle: upload, content storage, text
  extraction, chunk orchestration (`DocumentLibraryService`,
  `DocumentProcessingService`).
- `gabriel/knowledge/` owns chunk vectors, embeddings, knowledge sources, and
  retrieval (`ChunkVectorStore`, `EmbeddingProviderRegistry`,
  `KnowledgeSourceService`, `KnowledgeRetriever`).

### 2. Documents and knowledge sources are Universal Resources; chunks are not

Document metadata and knowledge sources get GRNs, versions, lifecycle events, and
PEEL enforcement like every other resource. Chunks are **derived data** — they are
rebuilt on every (re)process, carry the source document GRN plus position, and live
in a plain `document_chunks` table. Raw file bytes live on a configurable local
filesystem content store (`GABRIEL_CONTENT_ROOT`, content-addressed by SHA-256),
never in the database.

### 3. pgvector for vector storage, with a dialect-aware fallback

- The Alembic migration (`k1e5f7a9b3c4`) creates `document_chunks` with an
  `embedding vector(768)` column, the `vector` extension, and an HNSW index using
  `vector_cosine_ops` — **on PostgreSQL only** (guarded by dialect).
- On SQLite (tests, local dev) the column stays JSON and similarity is computed
  in-process with the same cosine metric, so the whole slice is testable without
  Postgres.
- Search is cosine-similarity (`<=>` operator on Postgres), org-scoped, and
  filterable by knowledge source GRNs and/or document GRNs.

### 4. Hot-swappable embedding providers, Ollama by default

`EmbeddingProviderRegistry` mirrors the Phase-3 LLM `ProviderRegistry`: providers
implement a small `EmbeddingProvider` protocol (`name`, `model`, `async embed`),
register by name, and can be swapped at runtime. The default is
`OllamaEmbeddingProvider` (`nomic-embed-text`, 768 dimensions, `GABRIEL_OLLAMA_BASE_URL`).
Chunks record the `embedding_model` used so mixed-model corpora stay detectable.

### 5. Graceful degradation when embeddings are unavailable

Embedding failures never block the document pipeline or chat:

- Processing stores chunks **without** vectors and marks the document
  `metadata.embedded = false`.
- Search and RAG retrieval fall back to keyword (`ILIKE`) matching when the query
  cannot be embedded.
- `KnowledgeRetriever.retrieve()` never raises — a failed retrieval yields an empty
  context, not a broken turn.

### 6. RAG integrates through the existing prompt pipeline

Retrieval does not bypass Phase 3: retrieved chunks become `ContextBlock`s (source
`knowledge:{filename}#chunk{n}`, bounded by a character budget) fed into the same
`PromptAssembler` used for memory. Retrieval is scoped to the agent's declared
`knowledge_sources`; agents without sources skip retrieval entirely. The gateway
emits an SSE `context` event so clients can display which chunks grounded a reply.

### 7. One knowledge source per document in V1

Membership is a nullable `knowledge_source_grn` column on documents (and denormalized
onto chunks for fast filtered search), not a join table. Attach/detach re-labels
chunks and maintains `document_count`. Many-to-many membership is deferred until a
real need appears.

## Consequences

- **Positive:** fully org-scoped RAG with zero new infrastructure required for dev
  and CI (SQLite fallback); embedding vendors swappable without touching call sites;
  chat robustness — embedding outages degrade to keyword retrieval instead of errors;
  reprocessing is idempotent (chunks are rebuilt, content is content-addressed).
- **Negative / accepted trade-offs:** the 768-dimension column is fixed per
  migration — switching to a different-dimension model requires a new migration and
  re-embedding; in-process cosine on SQLite does not scale (acceptable for tests);
  one-source-per-document limits sharing a document across collections in V1.
- **Follow-ups:** PDF/DOCX extraction quality passes, background processing queue,
  re-embedding jobs on model change, many-to-many source membership if needed.
