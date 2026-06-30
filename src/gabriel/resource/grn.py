from dataclasses import dataclass
from uuid_extensions import uuid7

from gabriel.resource.exceptions import InvalidGRNError

GRN_SCHEME = "grn"

@dataclass(frozen=True)
class GRN:
    """
    Operational Definition of a GRN (Gabriel Resource Name):

    A GRN is a globally unique, structured identifier used to reference
    any resource within the Gabriel system.

    Format:
        grn:<org_id>:<resource_type>/<resource_id>:<version>

    Components:
        - org_id:         The owning organization or tenant namespace.
        - resource_type:  The registered type of resource (e.g., user, agent, file).
        - resource_id:    A globally unique identifier for the resource instance.
                          Must be unique within org + resource_type scope.
        - version:        Monotonically increasing version of the resource state.
                          Used for optimistic concurrency and lifecycle control.

    Properties:
        - Globally unique within the Gabriel ecosystem
        - Immutable once created (except version increments)
        - Human-readable and machine-parseable
        - Scoped by organization for multi-tenancy isolation
    """

    org_id: str
    resource_type: str
    resource_id: str
    version: int = 1

    def __str__(self) -> str:
        """Return formatted GRN string"""
        return (
            f"{GRN_SCHEME}:{self.org_id}:"
            f"{self.resource_type}/{self.resource_id}:"
            f"{self.version}"
        )

    def __repr__(self) -> str:
        # docs/learned/!r.md
        return f"GRN({str(self)!r})"
    
    @classmethod
    def _parse_colon(cls, raw: str) -> "GRN":
        """Parse a GRN of the form:
            - grn:<org_id>:<resource_type>/<resource_id>:<version>

        raise InvalidGRNError if malformed
        """
        try:
            body = raw[len(f"{GRN_SCHEME}:"):]
            org_id, remainder = body.split(":", 1)
            type_and_id, version_str = remainder.rsplit(":", 1)
            resource_type, resource_id = type_and_id.split("/", 1)

            version = int(version_str)

            if version < 1:
                raise ValueError
            
        except(ValueError, TypeError):
            raise InvalidGRNError(f"Malformed GRN: {raw}") from None
        
        return cls(
            org_id=org_id,
            resource_type=resource_type,
            resource_id=resource_id,
            version=version,
        )

    @classmethod
    def parse(cls, raw: str) -> "GRN":
        """        
        Parse a GRN of the form:
            - grn:<org_id>:<resource_type>/<resource_id>:<version>

        raise InvalidGRNError if malformed
        """
        if raw.startswith(f"{GRN_SCHEME}:"):
            return cls._parse_colon(raw)
        raise InvalidGRNError(f"Invalid GRN scheme: {raw}")
    
    @classmethod
    def generate(cls, org_id: str, resource_type: str) -> "GRN":
        """
        Generate a new GRN.
        """
        
        return cls(
            org_id=org_id,
            resource_type=resource_type,
            resource_id=str(uuid7()),
            version=1,
        )