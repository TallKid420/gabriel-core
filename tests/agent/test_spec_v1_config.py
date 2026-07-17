"""V1 agent configuration — disabled tools & document collections."""
from gabriel.agent.specification import AgentSpecification


def test_effective_tool_names_subtracts_disabled() -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="default",
        model="gpt-test",
        tools=["search", "calculator", "clock"],
        disabled_tools=["clock"],
    )
    assert spec.effective_tool_names() == ["search", "calculator"]
    assert spec.disabled_tool_names() == ["clock"]


def test_disabled_tools_default_empty() -> None:
    spec = AgentSpecification(name="assistant", runtime="default", model="gpt-test")
    assert spec.disabled_tools == []
    assert spec.effective_tool_names() == []


def test_grounding_source_grns_merges_and_dedupes() -> None:
    ks = "grn:acme:knowledge_source/aaaa:1"
    dc = "grn:acme:knowledge_source/bbbb:1"
    spec = AgentSpecification(
        name="assistant",
        runtime="default",
        model="gpt-test",
        knowledge_sources=[ks],
        document_collections=[dc, ks],
    )
    assert spec.grounding_source_grns() == [ks, dc]


def test_document_collections_default_empty() -> None:
    spec = AgentSpecification(name="assistant", runtime="default", model="gpt-test")
    assert spec.document_collections == []
    assert spec.grounding_source_grns() == []
