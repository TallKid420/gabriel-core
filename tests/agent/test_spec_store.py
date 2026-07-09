"""Tests for the file-based AgentSpecification persistence store (Phase 4)."""

import pytest

from gabriel.agent.specification import AgentSpecification
from gabriel.agent.store import AgentSpecificationStore, SpecificationNotFoundError
from gabriel.agent.templates import build_specification, list_templates


def test_save_and_load_roundtrip_json(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    spec = build_specification("chat")
    path = store.save(spec)
    assert path.exists()
    assert path.suffix == ".json"

    loaded = store.load(spec.name)
    assert loaded == spec  # full pydantic equality (incl. memory + runtime_config)


def test_load_missing_raises(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    with pytest.raises(SpecificationNotFoundError):
        store.load("does-not-exist")


def test_list_and_exists(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    store.save(build_specification("chat", name="a"))
    store.save(build_specification("engineer", name="b"))
    assert store.list() == ["a", "b"]
    assert store.exists("a")
    assert not store.exists("c")


def test_delete(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    store.save(build_specification("chat", name="a"))
    store.delete("a")
    assert not store.exists("a")
    with pytest.raises(SpecificationNotFoundError):
        store.delete("a")


def test_save_many_and_load_all(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    specs = [build_specification(k, name=k) for k in list_templates()]
    paths = store.save_many(specs)
    assert len(paths) == len(specs)

    loaded = store.load_all()
    assert set(loaded) == set(list_templates())
    for key in list_templates():
        assert loaded[key] == build_specification(key, name=key)


def test_yaml_roundtrip_mirrors_agents_yaml(tmp_path) -> None:
    pytest.importorskip("yaml")
    store = AgentSpecificationStore(tmp_path, fmt="yaml")
    spec = build_specification("chat")
    path = store.save(spec)
    assert path.suffix == ".yaml"
    loaded = store.load(spec.name)
    assert loaded == spec


def test_store_reads_both_formats(tmp_path) -> None:
    pytest.importorskip("yaml")
    json_store = AgentSpecificationStore(tmp_path, fmt="json")
    yaml_store = AgentSpecificationStore(tmp_path, fmt="yaml")
    json_store.save(build_specification("chat", name="json-spec"))
    yaml_store.save(build_specification("server", name="yaml-spec"))

    # A json-default store can still load a yaml file and vice versa.
    assert json_store.load("yaml-spec").name == "yaml-spec"
    assert yaml_store.load("json-spec").name == "json-spec"


def test_name_sanitization(tmp_path) -> None:
    store = AgentSpecificationStore(tmp_path)
    spec = AgentSpecification(name="team/chat bot:v1", runtime="langgraph", model="gpt-5")
    path = store.save(spec)
    # Slashes/colons/spaces are sanitized into a safe stem.
    assert "/" not in path.name
    assert store.load("team/chat bot:v1").name == "team/chat bot:v1"
