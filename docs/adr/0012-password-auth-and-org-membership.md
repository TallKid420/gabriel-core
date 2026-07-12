# ADR-012: Password Authentication, Refresh Tokens & Organization Membership (Phase 1)

**Date:** 2026-07-12
**Status:** ✅ IMPLEMENTED
**Milestone:** Phase 1 — Core Backend Foundations

## Context

Phase 1 requires a production-usable authentication path and real
multi-tenant user management. The gateway already had:

- A hot-swappable `IdentityService` with a `ProviderRegistry` strategy
  pattern (`dev` header provider, `production` OIDC-shaped provider).
- JWT session issuance (`TokenService`) and principal → resource mirroring
  (ADR-001).
- `Organization` resources with org-scoped GRNs and PEEL authorization.

What was missing: first-party credentials (email/password), refresh tokens,
persistent `User` resources tied to principals, and organization
*membership* (who belongs to which org, with what role). This ADR records
the decisions made while adding those pieces.

## Decision

1. **Password identity provider (strategy, not special case).**
   Email/password login is implemented as a regular `IdentityProvider`
   (`gabriel/identity/providers/password.py`, name `"password"`) registered
   in **all** environments alongside `dev` (dev only) and `production`.
   The provider authenticates against the `users` table via an injected
   async session factory and returns the same session-view shape the other
   providers produce, so `IdentityService.login()` needs no changes.

2. **PBKDF2-HMAC-SHA256 for password hashing (stdlib only).**
   `gabriel/identity/passwords.py` uses `hashlib.pbkdf2_hmac` with a
   600k-iteration default, per-password random salt, and a
   self-describing `pbkdf2_sha256$<iterations>$<salt>$<hash>` format with
   constant-time comparison and `needs_rehash()` for future parameter
   bumps. Rationale: no new runtime dependencies (argon2/bcrypt would add
   compiled wheels); PBKDF2 at this cost is OWASP-acceptable and can be
   swapped later because the format is versioned.

3. **Opaque, rotated refresh tokens with reuse detection.**
   `gabriel/identity/refresh.py` stores only SHA-256 hashes of opaque
   random tokens (`refresh_tokens` table) with per-token expiry, a
   `family_id`, and a `replaced_by` chain. `rotate()` revokes the used
   token and issues a successor; presenting an already-rotated or revoked
   token revokes the **entire family** (theft/replay detection) and fails.
   Refresh tokens are only issued for `password` logins — dev principals
   are not persisted users.

4. **User resources mirror principals (extends ADR-001).**
   `User` is a first-class `Resource` (GRN type `user`) with a dedicated
   ORM slice (`gabriel/user/`): model → mapper → repository → service.
   Each user owns exactly one `Principal` (`principal_id` unique) so
   existing token issuance, PEEL evaluation, and event attribution work
   unchanged. `User.public_view()` and serialization exclude
   `password_hash`. Emails are unique **per organization**
   (`UniqueConstraint(org_id, email)`), preserving tenant isolation.

5. **Organization membership with role → capability mapping.**
   `org_memberships` links principals to organizations with an `OrgRole`
   (`OWNER > ADMIN > MEMBER > VIEWER`). `capabilities_for_role()`
   translates roles into the existing capability vocabulary consumed by
   PEEL, instead of inventing a parallel permission system.
   `MembershipService` enforces invariants — notably the *last-owner
   guard*: an organization can never lose its final `OWNER` via role
   change or removal.

6. **Atomic registration.**
   `RegistrationService.register()` creates organization + owner user +
   principal + membership + audit event in a single transaction; partial
   signups cannot exist. When no organization name is supplied, a personal
   org is derived from the email local part with `-2..-99` suffix
   de-duplication.

7. **API surface.**
   - `POST /auth/register` (201) → org + owner, returns access + refresh
     tokens (logs in through the registry, not a side channel).
   - `POST /auth/login` returns a `refresh_token` for the password method;
     `POST /auth/refresh` rotates; `POST /auth/logout` revokes.
   - `/users` and `/organizations/{org_id}/members` routers perform
     explicit same-org GRN checks (`_require_same_org`, `_require_org`)
     and admin-role checks on top of PEEL middleware.
   - Organization creation is deliberately **only** available through
     registration in Phase 1.

8. **Migrations.** A single Alembic revision
   (`i9c3d5e7f1a2`) merges the three previously divergent heads and adds
   `users`, `org_memberships`, and `refresh_tokens`. Timestamps use
   Python-side `default=utcnow` (not `server_default=now()`) so the
   SQLite fallback database keeps working.

## Consequences

- Email/password auth works in dev and production with zero configuration,
  while remaining replaceable via the provider registry (e.g. by an SSO
  provider later).
- Stolen refresh tokens are limited by rotation + family revocation, but
  access-token lifetime is still the exposure window — short TTLs remain
  important.
- PBKDF2 is intentionally an interim choice; `needs_rehash()` plus the
  versioned hash format give a migration path to argon2id without a
  breaking change.
- Per-org email uniqueness means the same email can exist in multiple
  organizations as distinct users; global account linking is out of scope
  for Phase 1.
- `test_production_disables_dev_provider` was updated: production now
  exposes `password` + `production` methods (dev remains excluded).
