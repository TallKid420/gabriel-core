# M1 — Identity Service

Authentication boundary for Gabriel Core: a pluggable Identity Service that
verifies credentials, issues **signed JWTs** carrying identity + capabilities,
and lets internal services trust those tokens without re-authenticating
(ADR-007). Authorization stays with PEEL (ADR-008/019) — this milestone only
does authentication.

## What was built

| Component | File(s) | Purpose |
|-----------|---------|---------|
| **Config** | `identity/config.py` | `IdentitySettings` frozen dataclass, `from_env()`. `is_production` forces dev auth off. |
| **Provider base** | `identity/providers/base.py` | `IdentityProvider` ABC + `AuthenticationResult`. The extension seam. |
| **Registry** | `identity/providers/registry.py` | Maps a method name (`dev`, `password`, `google`, …) → provider. |
| **Dev provider** | `identity/providers/dev.py` | Hardcoded dev principals by `userId`. **Refuses to construct in production.** |
| **Identity Service** | `identity/identity_service.py` | Orchestrates login → token, token → principal, JWKS, method discovery. `build_default_identity_service()` wires the default provider set. |
| **JWT infra** | `identity/keys.py`, `identity/auth.py` | Extended existing `KeyManager`/`TokenService`: RFC-7638 `kid`, key rotation, JWKS, per-kid verification. |
| **API** | `api/routers/auth.py`, `api/auth.py`, `api/middleware.py`, `api/dependencies.py`, `api/errors.py` | Endpoints + session-validation middleware. |

### Endpoints
- `POST /auth/login` — `{method, credentials}` → signed token + session, sets session cookie.
- `POST /auth/logout` — clears the session cookie.
- `GET /auth/me` — current principal from the verified token.
- `GET /auth/jwks` — public keys for offline token verification.
- Compat: `GET /auth/dev/principals`, `POST /auth/dev/login`, `GET /auth/session`.

Middleware authenticates every non-public request from an `Authorization: Bearer`
header **or** the session cookie, verifies the JWT, reconstructs the `Principal`,
and populates the `ExecutionContext` PEEL reads from.

## How future auth plugs in
Add a class implementing `IdentityProvider` (`name` + async `authenticate`) and
register it. No changes to the service, middleware, or endpoints. `POST /auth/login`
already routes by `method`, so password / Google / Entra / Okta / SAML / passkeys
are additive.

## Key ADR decisions
- **ADR-007 (Universal Identity):** authentication happens once at the boundary and
  produces a signed token; internal services trust it. Key rotation retains prior
  public keys so in-flight tokens keep verifying.
- **ADR-008 / ADR-019 (distributed PEEL):** capabilities are embedded in the *signed*
  token by the server — the removed client-supplied `X-Capabilities` header (a
  forgeable bypass) is gone. This is what fixed the 18 previously-failing API tests.
- **ADR-001 / ADR-009:** principals keep their GRN identity and factory conventions.

## Deliberate simplifications (no over-engineering)
- Reused the existing `TokenService` / `KeyManager` instead of a new JWT stack.
- Frozen dataclass config instead of a settings framework.
- Dev provider is a single small module; production safety is a hard constructor guard.

## Known limitations / follow-ups
- **Key storage:** keys are ephemeral per process unless `GABRIEL_JWT_PRIVATE_KEY_PATH` /
  `GABRIEL_JWT_PUBLIC_KEY_PATH` are set. Production must mount PEMs (or a secrets manager).
- **Logout** clears the cookie only; there is no server-side revocation list yet.
- **Rotation** is in-process (`KeyManager.rotate()`); no scheduled/persisted rotation.
- **Real providers** (password, OAuth, SAML, passkeys) and refresh tokens are future work.

## Configuration
| Env var | Default | Notes |
|---------|---------|-------|
| `GABRIEL_ENV` | `development` | `production` disables the dev provider. |
| `GABRIEL_JWT_TOKEN_TTL_SECONDS` | `3600` | Access-token lifetime. |
| `GABRIEL_SESSION_COOKIE_NAME` | `gabriel_session` | |
| `GABRIEL_SESSION_COOKIE_SECURE` | `false` | Set `true` behind HTTPS. |
| `GABRIEL_JWT_PRIVATE_KEY_PATH` / `_PUBLIC_KEY_PATH` | unset | Mount real signing keys in prod. |
| `GABRIEL_DEV_AUTH_ENABLED` | `true` (non-prod) | Forced off in production. |

## Tests
- `tests/identity/test_providers.py` — registry + dev provider (incl. production guard).
- `tests/identity/test_keys_rotation.py` — kid stability, rotation, JWKS.
- `tests/identity/test_identity_service.py` — login/verify round-trip, cross-key rejection, rotation.
- `tests/api/test_auth.py` — endpoint behavior, forged-token rejection, cookie auth.
- Full suite: **321 passed, 1 skipped** (the 18 pre-existing auth failures are resolved).
