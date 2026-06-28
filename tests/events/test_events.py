"""Comprehensive tests for CQRS + Event Sourcing."""
import pytest

from gabriel.events import (
    Command,
    Event,
    EventStore,
    Dispatcher,
    CreateOrganizationHandler,
    OrganizationProjection,
    HandlerNotFoundError,
    CommandValidationError,
)


class TestEvent:
    """Tests for Event model."""

    def test_event_creation(self):
        """Test creating an event."""
        event = Event(
            type="organization_created",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            resource_grn="grn://acme/organization/acme",
            payload={"display_name": "Acme Corp"},
        )
        assert event.type == "organization_created"
        assert event.id  # UUID generated
        assert event.occurred_at  # timestamp set
        assert event.principal_id == "principal://acme/user/alice"

    def test_event_immutable(self):
        """Test that events are immutable."""
        event = Event(
            type="test",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        with pytest.raises(Exception):  # frozen Pydantic model
            event.type = "changed"

    def test_event_correlation_id(self):
        """Test correlation ID for tracing."""
        correlation_id = "trace-123"
        event = Event(
            type="test",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id=correlation_id,
        )
        assert event.correlation_id == correlation_id

    def test_event_causation_id(self):
        """Test causation ID for causal ordering."""
        event1 = Event(
            type="event1",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        event2 = Event(
            type="event2",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            causation_id=event1.id,
        )
        assert event2.causation_id == event1.id


class TestCommand:
    """Tests for Command model."""

    def test_command_creation(self):
        """Test creating a command."""
        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={"display_name": "Acme Corp"},
        )
        assert command.type == "create_organization"
        assert command.id  # UUID generated
        assert command.issued_at  # timestamp set
        assert command.payload["display_name"] == "Acme Corp"

    def test_command_immutable(self):
        """Test that commands are immutable."""
        command = Command(
            type="test",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        with pytest.raises(Exception):  # frozen Pydantic model
            command.type = "changed"

    def test_command_correlation_id(self):
        """Test correlation ID for tracing."""
        correlation_id = "trace-456"
        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id=correlation_id,
        )
        assert command.correlation_id == correlation_id


class TestEventStore:
    """Tests for append-only event store."""

    def test_append_event(self):
        """Test appending an event."""
        store = EventStore()
        event = Event(
            type="test",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        store.append(event)
        assert store.count() == 1

    def test_append_multiple_events(self):
        """Test appending multiple events."""
        store = EventStore()
        events = [
            Event(
                type="test1",
                principal_id="principal://acme/user/alice",
                organization_id="acme",
            ),
            Event(
                type="test2",
                principal_id="principal://acme/user/bob",
                organization_id="acme",
            ),
        ]
        store.append_many(events)
        assert store.count() == 2

    def test_events_for_organization(self):
        """Test querying events by organization."""
        store = EventStore()
        event1 = Event(
            type="test",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        event2 = Event(
            type="test",
            principal_id="principal://other/user/bob",
            organization_id="other",
        )
        store.append_many([event1, event2])
        acme_events = store.events_for_organization("acme")
        assert len(acme_events) == 1
        assert acme_events[0].organization_id == "acme"

    def test_events_by_type(self):
        """Test querying events by type."""
        store = EventStore()
        event1 = Event(
            type="organization_created",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        event2 = Event(
            type="agent_executed",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )
        store.append_many([event1, event2])
        created_events = store.events_by_type("organization_created")
        assert len(created_events) == 1
        assert created_events[0].type == "organization_created"

    def test_events_for_resource(self):
        """Test querying events by resource."""
        store = EventStore()
        grn = "grn://acme/organization/acme"
        event1 = Event(
            type="organization_created",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            resource_grn=grn,
        )
        event2 = Event(
            type="other_event",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            resource_grn="grn://other",
        )
        store.append_many([event1, event2])
        org_events = store.events_for_resource(grn)
        assert len(org_events) == 1
        assert org_events[0].resource_grn == grn

    def test_events_by_correlation_id(self):
        """Test querying events by correlation ID."""
        store = EventStore()
        correlation_id = "trace-789"
        event1 = Event(
            type="test1",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id=correlation_id,
        )
        event2 = Event(
            type="test2",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id=correlation_id,
        )
        event3 = Event(
            type="test3",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id="other",
        )
        store.append_many([event1, event2, event3])
        traced_events = store.events_by_correlation_id(correlation_id)
        assert len(traced_events) == 2


class TestDispatcher:
    """Tests for command dispatcher."""

    @pytest.fixture
    def setup(self):
        """Setup dispatcher with store, handler, and projection."""
        store = EventStore()
        dispatcher = Dispatcher(store)
        handler = CreateOrganizationHandler()
        projection = OrganizationProjection()

        dispatcher.register_handler(handler)
        dispatcher.register_projection(projection)

        return store, dispatcher, projection

    @pytest.mark.asyncio
    async def test_command_dispatch(self, setup):
        """Test dispatching a command."""
        store, dispatcher, projection = setup

        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={"display_name": "Acme Corp"},
        )

        events = await dispatcher.dispatch(command)

        assert len(events) == 1
        assert events[0].type == "organization_created"
        assert events[0].payload["display_name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_event_stored(self, setup):
        """Test that events are stored."""
        store, dispatcher, projection = setup

        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={"display_name": "Acme Corp"},
        )

        await dispatcher.dispatch(command)

        assert store.count() == 1
        assert store.events()[0].type == "organization_created"

    @pytest.mark.asyncio
    async def test_projection_updated(self, setup):
        """Test that projections are updated."""
        store, dispatcher, projection = setup

        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={"display_name": "Acme Corp"},
        )

        events = await dispatcher.dispatch(command)
        grn = events[0].resource_grn

        org = projection.get_organization(grn)
        assert org is not None
        assert org["display_name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_handler_not_found(self, setup):
        """Test error when handler not found."""
        store, dispatcher, projection = setup

        command = Command(
            type="unknown_command",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
        )

        with pytest.raises(HandlerNotFoundError):
            await dispatcher.dispatch(command)

    @pytest.mark.asyncio
    async def test_command_validation_error(self, setup):
        """Test validation error in handler."""
        store, dispatcher, projection = setup

        # display_name is required
        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={},  # Missing display_name
        )

        with pytest.raises(CommandValidationError):
            await dispatcher.dispatch(command)

    @pytest.mark.asyncio
    async def test_correlation_id_propagated(self, setup):
        """Test that correlation IDs are propagated to events."""
        store, dispatcher, projection = setup

        correlation_id = "trace-xyz"
        command = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            correlation_id=correlation_id,
            payload={"display_name": "Acme Corp"},
        )

        events = await dispatcher.dispatch(command)

        assert events[0].correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_event_replay(self, setup):
        """Test replaying events to rebuild projection."""
        store, dispatcher, projection = setup

        # Dispatch first command
        command1 = Command(
            type="create_organization",
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            payload={"display_name": "Acme Corp"},
        )
        await dispatcher.dispatch(command1)

        # Dispatch second command
        command2 = Command(
            type="create_organization",
            principal_id="principal://acme/user/bob",
            organization_id="acme",
            payload={"display_name": "Beta Corp"},
        )
        await dispatcher.dispatch(command2)

        # Now reset projection
        await dispatcher.replay_events(store.events())

        # Should have both organizations
        orgs = projection.list_organizations()
        assert len(orgs) == 2
        assert {org["display_name"] for org in orgs} == {"Acme Corp", "Beta Corp"}

    @pytest.mark.asyncio
    async def test_multiple_organizations_projection(self, setup):
        """Test projection with multiple organizations."""
        store, dispatcher, projection = setup

        for i, name in enumerate(["Alpha Corp", "Beta Inc", "Gamma LLC"]):
            command = Command(
                type="create_organization",
                principal_id=f"principal://acme/user/user{i}",
                organization_id="acme",
                payload={"display_name": name},
            )
            await dispatcher.dispatch(command)

        orgs = projection.list_organizations()
        assert len(orgs) == 3
        assert {org["display_name"] for org in orgs} == {"Alpha Corp", "Beta Inc", "Gamma LLC"}
