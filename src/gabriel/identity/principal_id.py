"""PrincipalID: Unique identifier for identity primitives in Gabriel.

Similar to GRN for resources, PrincipalID is a globally unique, immutable identifier
for principals (users, agents, service accounts, system agents).

Format: principal://<org_id>/<principal_type>/<principal_identifier>

Example: principal://acme/user/alice@v1
"""
from dataclasses import dataclass

from gabriel.identity.exceptions import InvalidPrincipalIDError

PRINCIPAL_SCHEME = "principal"


@dataclass(frozen=True)
class PrincipalID:
    """Immutable, globally unique identifier for a Principal.
    
    Components:
        - org_id: The owning organization (tenant namespace).
        - principal_type: The type of principal (user, agent, system_agent, service_account).
        - principal_identifier: A unique identifier within the org/type scope.
    """

    org_id: str
    principal_type: str  # e.g., "user", "agent", "system_agent", "service_account"
    principal_identifier: str

    def __str__(self) -> str:
        """Return formatted PrincipalID string."""
        return (
            f"{PRINCIPAL_SCHEME}://{self.org_id}/"
            f"{self.principal_type}/{self.principal_identifier}"
        )

    def __repr__(self) -> str:
        return f"PrincipalID({str(self)!r})"

    @classmethod
    def parse(cls, raw: str) -> "PrincipalID":
        """Parse a PrincipalID of the form:
        principal://org_id/principal_type/principal_identifier
        
        Raises:
            InvalidPrincipalIDError: If malformed.
        """
        if not raw.startswith(f"{PRINCIPAL_SCHEME}://"):
            raise InvalidPrincipalIDError(f"Invalid PrincipalID scheme: {raw}")

        rest = raw[len(f"{PRINCIPAL_SCHEME}://") :]
        parts = rest.split("/")

        if len(parts) != 3:
            raise InvalidPrincipalIDError(
                f"Invalid PrincipalID format (expected 3 parts): {raw}"
            )

        org_id, principal_type, principal_identifier = parts

        if not org_id or not principal_type or not principal_identifier:
            raise InvalidPrincipalIDError(f"PrincipalID contains empty components: {raw}")

        return cls(
            org_id=org_id,
            principal_type=principal_type,
            principal_identifier=principal_identifier,
        )
