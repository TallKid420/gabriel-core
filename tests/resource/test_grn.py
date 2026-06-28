import pytest
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import InvalidGRNError

def test_generate_returns_valid_grn():
    grn = GRN.generate("acme", "agent")
    assert grn.org_id == "acme"
    assert grn.resource_type == "agent"
    assert grn.version == 1

def test_parse_valid_grn():
    grn = GRN.parse("grn://acme/agent/abc123@1")
    assert grn.org_id == "acme"
    assert grn.resource_id == "abc123"

def test_parse_invalid_grn_raises():
    with pytest.raises(InvalidGRNError):
        GRN.parse("not-a-grn")

def test_grn_str_roundtrip():
    grn = GRN.generate("acme", "agent")
    assert GRN.parse(str(grn)) == grn