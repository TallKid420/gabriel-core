# Merge Order & Readiness — Core Phase PRs

This document records the recommended merge sequence for the four core backend phase
pull requests and the results of a merge-readiness review.

## TL;DR

The four PRs form a **linear stack** — each branch was cut from the previous phase's
head, so they must be merged **in ascending order**:

```
#3  Phase 1  →  #4  Phase 2  →  #5  Phase 3  →  #6  Phase 4
```

As of this review, **all four PRs have already been merged into `main`** in that order,
and the merges were **clean** (verified below). No conflicts require resolution.

## The pull requests

| PR | Branch | Base | Scope |
|----|--------|------|-------|
| [#3](https://github.com/TallKid420/gabriel-core/pull/3) | `feature/phase1-core-backend-foundations` | `main` | JWT auth, password login + refresh tokens, User/Org management, multi-tenancy, PEEL foundations |
| [#4](https://github.com/TallKid420/gabriel-core/pull/4) | `feature/phase2-core-business-logic` | `main` | Conversations, Messages, Agent management, Notifications, Memory layers |
| [#5](https://github.com/TallKid420/gabriel-core/pull/5) | `feature/phase3-gateway-ai-runtime` | `main` | Gateway AI runtime — Ollama provider, streaming SSE chat, tools, sessions |
| [#6](https://github.com/TallKid420/gabriel-core/pull/6) | `feature/phase4-document-knowledge` | `main` | Document upload, chunking, pgvector embeddings, RAG, knowledge sources |

## Why the order matters

The feature branches were **stacked**, not developed in parallel from a common base:

- Phase 2 (#4) was branched from the Phase 1 (#3) head.
- Phase 3 (#5) was branched from the Phase 2 (#4) head.
- Phase 4 (#6) was branched from the Phase 3 (#5) head.

Because of this, each PR's diff (before merge) contained the commits of all earlier,
not-yet-merged phases. Merging out of order — for example #6 before #3 — would either
fail or pull later work in ahead of its dependencies. Ascending order (#3 → #4 → #5 →
#6) is the only correct sequence, and once an earlier PR is merged the later PR's diff
naturally reduces to just its own changes.

Concrete cross-phase dependencies that make the ordering mandatory:

- **#4 depends on #3:** the domain slices rely on the resource/GRN, event-store, and
  PEEL foundations and the authenticated principal/organization model from Phase 1.
- **#5 depends on #4:** the Gateway persists messages and reads agents through the
  Phase 2 conversation/agent services; it stores no business data of its own.
- **#6 depends on #5:** RAG retrieval injects `ContextBlock`s into the Phase 3
  `PromptAssembler` and hooks into `ChatRuntimeService.stream_turn`; the agent
  `knowledge_sources` field extends the Phase 2/3 agent spec.

## Merge-readiness review

- **Conflicts:** none. Because the branches are a linear stack, merging in ascending
  order applies cleanly with no overlapping edits to resolve.
- **Verification:** after all four merges, `main`'s tree is **byte-for-byte identical**
  to the Phase 4 branch head (`caf82f9`). This confirms the stacked merges introduced no
  divergence and no conflict-resolution edits altered content.
- **Single Alembic head:** the migrations chain linearly
  (`… → i9c3d5e7f1a2 → j0d4e6f8a2b3 → k1e5f7a9b3c4`) and resolve to a single head, so
  `alembic upgrade head` works after all phases are merged. No branching migrations.
- **Shared files touched by multiple phases** (e.g. `src/gabriel/api/app.py`,
  `src/gabriel/api/dependencies.py`, `src/gabriel/resource/models.py`,
  `src/gabriel/policy/capabilities.py`, `alembic/env.py`): each later phase **appended**
  to these (new router includes, new capability mappings, new ORM imports) rather than
  rewriting earlier phases' lines, which is why the stacked merges stayed conflict-free.
  If any of these PRs had been rebased onto a diverged `main`, these are the files to
  watch for conflicts.

## Test baseline note

The full suite finishes with a known baseline of pre-existing failures inherited from
before these documentation changes (18 failing / 551 passing at the Phase 4 head). These
failures are unrelated to merge order — they exist on the phase branches themselves — and
were documented in the Phase 4 PR (#6). New work should compare against this baseline
rather than expecting a fully green suite until those pre-existing failures are
separately addressed.

## Recommendation

1. Merge in ascending order: **#3 → #4 → #5 → #6** (already done on `main`).
2. After each merge, run `alembic upgrade head` and `pytest` to confirm the incremental
   state is healthy.
3. This Phase 6 documentation PR is based on the post-merge `main` and touches only docs
   and local-dev tooling (README, `docs/`, `docker-compose.yml`), so it carries **no**
   ordering constraints and can be merged independently.
