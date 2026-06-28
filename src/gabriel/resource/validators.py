"""Resource validators that enforce rules on resource creation/updates."""
from typing import Any
from pydantic import ValidationError

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.exceptions import ResourceValidationError


class ResourceValidator:
    """Validates resources against their type's rules.
    
    Uses descriptor-provided validators plus built-in validation.
    """
    
    def __init__(self, descriptor: ResourceDescriptor) -> None:
        """Initialize validator with descriptor metadata.
        
        Args:
            descriptor: ResourceDescriptor containing validation rules.
        """
        self.descriptor = descriptor
    
    def validate(self, resource: Any) -> bool:
        """Validate a resource instance.
        
        Args:
            resource: The resource to validate.
            
        Returns:
            True if valid.
            
        Raises:
            ResourceValidationError: If validation fails.
        """
        # Check 1: Instance must be of the correct type
        if not isinstance(resource, self.descriptor.model):
            raise ResourceValidationError(
                f"Resource is not an instance of {self.descriptor.model.__name__}. "
                f"Got {type(resource).__name__}."
            )
        
        # Check 2: If descriptor has custom validator, call it
        if self.descriptor.validator_fn is not None:
            try:
                if not self.descriptor.validator_fn(resource):
                    raise ResourceValidationError(
                        f"Custom validator failed for {self.descriptor.type_name}"
                    )
            except Exception as e:
                raise ResourceValidationError(
                    f"Custom validator raised exception: {e}"
                ) from e
        
        # Check 3: Try to validate the Pydantic model (this will catch type errors, etc)
        try:
            self.descriptor.model.model_validate(resource.model_dump())
        except ValidationError as e:
            raise ResourceValidationError(
                f"Pydantic validation failed: {e}"
            ) from e
        
        return True
    
    def validate_batch(self, resources: list[Any]) -> list[bool]:
        """Validate multiple resources.
        
        Args:
            resources: List of resources to validate.
            
        Returns:
            List of validation results (True for each valid resource).
            
        Raises:
            ResourceValidationError: If any resource fails validation.
        """
        results = []
        for resource in resources:
            results.append(self.validate(resource))
        return results
