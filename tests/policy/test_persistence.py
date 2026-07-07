import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.api.dependencies import PolicyCommandHandler
from gabriel.database.base import Base
from gabriel.events import Command, Dispatcher, EventStore
from gabriel.policy.engine import EvaluationRequest, PolicyEngine
from gabriel.policy.models import Effect, PolicyStatement
from gabriel.policy.repository import PolicyRepository
from gabriel.policy.service import PolicyService
from gabriel.resource.exceptions import ResourceNotFoundError


@pytest.mark.asyncio
async def test_policies_survive_restart(tmp_path):
    db_path = tmp_path / "policy_restart.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    statement = PolicyStatement(
        effect=Effect.ALLOW,
        principal_match="*",
        action_match="resource:read",
        resource_match="*",
    )

    async with session_factory() as session:
        service = PolicyService(PolicyRepository(session))
        await service.create_policy(
            org_id="acme",
            created_by="principal://acme/user/admin",
            statements=[statement],
            policy_grn="grn:acme:policy/default:1",
        )

    await engine.dispose()

    restart_engine = create_async_engine(database_url, echo=False)
    restart_factory = async_sessionmaker(restart_engine, expire_on_commit=False, class_=AsyncSession)

    async with restart_factory() as session:
        service = PolicyService(PolicyRepository(session))
        policies = await service.list_policies("acme")

    await restart_engine.dispose()

    assert len(policies) == 1
    assert str(policies[0].grn) == "grn:acme:policy/default:1"
    assert policies[0].statements[0].action_match == "resource:read"


@pytest.mark.asyncio
async def test_peel_engine_loads_policies_from_database(db_session):
    statement = PolicyStatement(
        effect=Effect.ALLOW,
        principal_match="principal://acme/user/*",
        action_match="resource:read",
        resource_match="*",
    )

    service = PolicyService(PolicyRepository(db_session))
    await service.create_policy(
        org_id="acme",
        created_by="principal://acme/user/admin",
        statements=[statement],
        policy_grn="grn:acme:policy/read-allow:1",
    )

    loaded_policies = await service.list_policies("acme")
    engine = PolicyEngine(loaded_policies)

    decision = engine.evaluate(
        EvaluationRequest(
            principal="principal://acme/user/alice",
            action="resource:read",
            resource="grn:acme:document/1:1",
        )
    )

    assert decision == Effect.ALLOW


@pytest.mark.asyncio
async def test_policy_create_update_delete_commands_work_through_dispatcher(tmp_path):
    db_path = tmp_path / "policy_dispatcher.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    dispatcher = Dispatcher(event_store=EventStore())
    policy_engine = PolicyEngine([])

    # Register policy command handlers exactly as gateway wiring does.
    dispatcher.register_handler(
        PolicyCommandHandler(
            "create_policy",
            "policy_created",
            session_factory,
            policy_engine,
        )
    )
    dispatcher.register_handler(
        PolicyCommandHandler(
            "update_policy",
            "policy_updated",
            session_factory,
            policy_engine,
        )
    )
    dispatcher.register_handler(
        PolicyCommandHandler(
            "delete_policy",
            "policy_deleted",
            session_factory,
            policy_engine,
        )
    )

    create_command = Command(
        type="create_policy",
        principal_id="principal://acme/user/admin",
        organization_id="acme",
        payload={
            "grn": "grn:acme:policy/runtime:1",
            "statements": [
                {
                    "effect": "allow",
                    "principal_match": "*",
                    "action_match": "resource:read",
                    "resource_match": "*",
                }
            ],
        },
    )
    create_events = await dispatcher.dispatch(create_command)
    assert create_events[0].type == "policy_created"

    update_command = Command(
        type="update_policy",
        principal_id="principal://acme/user/admin",
        organization_id="acme",
        target_resource_grn="grn:acme:policy/runtime:1",
        payload={
            "statements": [
                {
                    "effect": "deny",
                    "principal_match": "*",
                    "action_match": "resource:delete",
                    "resource_match": "*",
                }
            ]
        },
    )
    update_events = await dispatcher.dispatch(update_command)
    assert update_events[0].type == "policy_updated"

    delete_command = Command(
        type="delete_policy",
        principal_id="principal://acme/user/admin",
        organization_id="acme",
        target_resource_grn="grn:acme:policy/runtime:1",
    )
    delete_events = await dispatcher.dispatch(delete_command)
    assert delete_events[0].type == "policy_deleted"

    async with session_factory() as session:
        repo = PolicyRepository(session)
        with pytest.raises(ResourceNotFoundError):
            await repo.get_by_grn("grn:acme:policy/runtime:1")

    await engine.dispose()
