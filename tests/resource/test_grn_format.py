"""Tests for GRN (Gabriel Resource Name) format consistency (Step-0 decision)."""
import pytest
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import InvalidGRNError


class TestGRNFormat:
    """Test GRN format: grn:<org_id>:<resource_type>/<resource_id>:<version>"""

    def test_grn_string_format(self):
        """Test GRN string format matches specification."""
        grn = GRN(
            org_id="acme",
            resource_type="organization",
            resource_id="org-123",
            version=1
        )
        
        grn_str = str(grn)
        
        # Format: grn:<org_id>:<resource_type>/<resource_id>:<version>
        expected = "grn:acme:organization/org-123:1"
        assert grn_str == expected

    def test_grn_format_with_different_versions(self):
        """Test GRN format with different version numbers."""
        for version in [1, 2, 10, 100]:
            grn = GRN(
                org_id="tenant-a",
                resource_type="agent",
                resource_id="agent-001",
                version=version
            )
            
            grn_str = str(grn)
            assert grn_str.endswith(f":{version}")

    def test_grn_parse_and_reformat(self):
        """Test that parsing and reformatting a GRN gives same string."""
        original_str = "grn:acme:user/alice:1"
        
        grn = GRN.parse(original_str)
        reformatted = str(grn)
        
        assert reformatted == original_str

    def test_grn_components_accessible(self):
        """Test that GRN components are accessible."""
        grn = GRN(
            org_id="myorg",
            resource_type="workflow",
            resource_id="workflow-42",
            version=5
        )
        
        assert grn.org_id == "myorg"
        assert grn.resource_type == "workflow"
        assert grn.resource_id == "workflow-42"
        assert grn.version == 5

    def test_grn_immutable(self):
        """Test that GRN is immutable (frozen dataclass)."""
        grn = GRN(
            org_id="test",
            resource_type="resource",
            resource_id="123",
            version=1
        )
        
        # Attempting to modify should raise AttributeError
        with pytest.raises(AttributeError):
            grn.version = 2

    def test_grn_equality(self):
        """Test GRN equality comparison."""
        grn1 = GRN(
            org_id="acme",
            resource_type="agent",
            resource_id="bot-1",
            version=1
        )
        
        grn2 = GRN(
            org_id="acme",
            resource_type="agent",
            resource_id="bot-1",
            version=1
        )
        
        grn3 = GRN(
            org_id="acme",
            resource_type="agent",
            resource_id="bot-1",
            version=2
        )
        
        assert grn1 == grn2
        assert grn1 != grn3

    def test_grn_parse_colon_format(self):
        """Test parsing GRN in colon format."""
        grn_str = "grn:myorg:solution/sol-abc:1"
        grn = GRN.parse(grn_str)
        
        assert grn.org_id == "myorg"
        assert grn.resource_type == "solution"
        assert grn.resource_id == "sol-abc"
        assert grn.version == 1

    def test_grn_parse_invalid_scheme_raises_error(self):
        """Test that invalid GRN scheme raises InvalidGRNError."""
        invalid_grn = "urn:acme:agent/bot:1"  # Should be 'grn' not 'urn'
        
        with pytest.raises(InvalidGRNError):
            GRN.parse(invalid_grn)

    def test_grn_parse_missing_parts_raises_error(self):
        """Test that incomplete GRN format raises InvalidGRNError."""
        invalid_grn = "grn:acme:agent"  # Missing resource_id and version
        
        with pytest.raises(InvalidGRNError):
            GRN.parse(invalid_grn)

    def test_grn_in_organization_context(self):
        """Test GRN format in Organization resource context."""
        # GRN for an organization should follow: grn:<org_id>:organization/<org_id>:<version>
        grn = GRN(
            org_id="acme",
            resource_type="organization",
            resource_id="acme",  # Often the same as org_id
            version=1
        )
        
        grn_str = str(grn)
        assert "acme" in grn_str
        assert "organization" in grn_str
        assert ":1" in grn_str

    def test_grn_in_principal_context(self):
        """Test GRN format in Principal resource context."""
        # Principals mirror PrincipalID: principal://org/type/id
        # Their GRN should be: grn:<org>:principal/<unique-id>:<version>
        grn = GRN(
            org_id="acme",
            resource_type="principal",
            resource_id="principal-alice-uuid",
            version=1
        )
        
        grn_str = str(grn)
        assert grn_str.startswith("grn:acme:principal/")
        assert ":1" in grn_str

    def test_grn_version_defaults_to_one(self):
        """Test that GRN version defaults to 1."""
        grn = GRN(
            org_id="test",
            resource_type="agent",
            resource_id="test-123"
        )
        
        # Should have default version 1
        assert grn.version == 1
        assert ":1" in str(grn)

    def test_grn_with_complex_resource_id(self):
        """Test GRN with complex resource IDs (UUIDs, etc)."""
        complex_ids = [
            "123e4567-e89b-12d3-a456-426614174000",  # UUID
            "org-resource-000000000000000000000001",  # Long ID
            "abc123",  # Short ID
        ]
        
        for resource_id in complex_ids:
            grn = GRN(
                org_id="acme",
                resource_type="resource",
                resource_id=resource_id,
                version=1
            )
            
            grn_str = str(grn)
            assert resource_id in grn_str

    def test_grn_repr_format(self):
        """Test GRN repr format is useful for debugging."""
        grn = GRN(
            org_id="acme",
            resource_type="agent",
            resource_id="bot-01",
            version=1
        )
        
        repr_str = repr(grn)
        # Should contain GRN indicator and the string representation
        assert "GRN" in repr_str
        assert "grn:acme:agent/bot-01:1" in repr_str
