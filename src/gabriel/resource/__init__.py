"""Gabriel resource subsystem exports."""

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import ResourceRegistry, registry
from gabriel.resource.schema import ResourceSchema
from gabriel.resource.serializer import ResourceSerializer
from gabriel.resource.validators import ResourceValidator

__all__ = [
	"ResourceDescriptor",
	"ResourceFactory",
	"ResourceRegistry",
	"ResourceSchema",
	"ResourceSerializer",
	"ResourceValidator",
	"registry",
]
