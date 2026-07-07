from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.api.app import create_app
from gabriel.database.base import Base
from gabriel.identity import (
	Capability,
	IdentitySettings,
	KeyManager,
	Principal,
	PrincipalID,
	PrincipalType,
	ProductionIdentityProvider,
	ProviderRegistry,
	TokenService,
)
from gabriel.identity.exceptions import IdentityConfigurationError
from gabriel.identity.identity_service import IdentityService, build_default_identity_service
from gabriel.identity.repository import PrincipalRepository

import gabriel.organization.orm  # noqa: F401
import gabriel.identity.orm  # noqa: F401
import gabriel.events.orm  # noqa: F401


def _build_production_identity_service(
	session_factory: async_sessionmaker[AsyncSession],
) -> IdentityService:
	settings = IdentitySettings(
		environment="production",
		dev_auth_enabled=False,
		session_cookie_secure=True,
	)
	key_manager = KeyManager()
	token_service = TokenService(key_manager, token_expiry_seconds=settings.token_ttl_seconds)
	registry = ProviderRegistry()
	registry.register(ProductionIdentityProvider(token_service, session_factory))
	return IdentityService(
		settings=settings,
		key_manager=key_manager,
		registry=registry,
		token_service=token_service,
	)


async def _persist_principal(session_factory: async_sessionmaker[AsyncSession]) -> Principal:
	principal = Principal(
		id=PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice"),
		organization_id="acme",
		principal_type=PrincipalType.USER,
		display_name="Alice",
		capabilities={Capability.AUTHENTICATE, Capability.READ_RESOURCE},
	)
	async with session_factory() as session:
		repo = PrincipalRepository(session)
		await repo.create(principal)
	return principal


def test_jwt_authenticated_request_succeeds_with_production_provider():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
	session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

	async def _setup() -> tuple[IdentityService, Principal]:
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
		service = _build_production_identity_service(session_factory)
		principal = await _persist_principal(session_factory)
		return service, principal

	identity_service, principal = asyncio.run(_setup())
	token = identity_service.token_service.issue(principal)

	app = create_app()
	with TestClient(app) as client:
		client.app.state.identity_service = identity_service
		response = client.get("/auth/me", headers={"Authorization": f"Bearer {token.value}"})

	asyncio.run(engine.dispose())

	assert response.status_code == 200
	assert response.json()["principal_id"] == str(principal.id)


def test_invalid_token_rejected_with_production_provider():
	engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
	session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

	async def _setup() -> IdentityService:
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
		return _build_production_identity_service(session_factory)

	identity_service = asyncio.run(_setup())

	app = create_app()
	with TestClient(app) as client:
		client.app.state.identity_service = identity_service
		response = client.get(
			"/auth/me",
			headers={"Authorization": "Bearer not-a-valid-jwt"},
		)

	asyncio.run(engine.dispose())

	assert response.status_code == 401


def test_dev_provider_blocked_in_production():
	with pytest.raises(IdentityConfigurationError):
		build_default_identity_service(
			IdentitySettings(environment="production", dev_auth_enabled=True)
		)
