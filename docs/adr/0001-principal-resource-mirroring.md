# ADR 0001: Principal identity primitive with resource mirror

Status: Accepted

## Context

Gabriel has two overlapping models for people and agents:

- `PrincipalID` / `Principal` for authentication and authorization context.
- GRN-addressable `Resource` objects for URM, PEEL, audit, and event handling.

The spec requires both of these truths to coexist:

- Every principal has a universal identity.
- Everything meaningful is a resource.

The identity path must remain fast and stable, so principals should stay keyed by `PrincipalID` rather than being forced through GRN lookup for every auth check.

## Decision

`Principal` remains the identity primitive keyed by `PrincipalID`.

Each principal is mirrored by a GRN-addressable `User` or `Agent` resource owned by the organization.

The persistence layer keeps a nullable `principals.resource_grn` link from the identity row to the mirrored resource.

## Consequences

- Authentication and token validation stay on `PrincipalID`.
- Authorization, audit, and URM flows can operate on the mirrored resource GRN.
- Identity and resource lifecycles remain linked, but are stored separately.
- New principal types should register both identity and resource sides together.

## Implementation Notes

- `Principal` now carries an optional `resource_grn` link in the domain model.
- `PrincipalORM` stores the nullable `resource_grn` and `metadata` fields.
- Mappers must translate between `PrincipalID` and the ORM string key.
- `Agent` already exists as the resource mirror; `User` should follow the same pattern when introduced.
