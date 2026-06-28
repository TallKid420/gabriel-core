"""Handler base class: Processes commands and emits events."""
from abc import ABC, abstractmethod

from gabriel.events.command import Command
from gabriel.events.event import Event


class Handler(ABC):
    """Base class for command handlers.
    
    Every command type has exactly one handler.
    A handler takes a command, validates/executes it, and returns events.
    
    Handlers never touch the database directly.
    They only return events, which are stored and projected.
    """

    @property
    @abstractmethod
    def command_type(self) -> str:
        """The command type this handler processes.
        
        Example: 'create_organization', 'execute_agent'
        """
        pass

    @abstractmethod
    async def handle(self, command: Command) -> list[Event]:
        """Process a command and return events.
        
        Args:
            command: The command to process.
            
        Returns:
            list[Event]: Events emitted by this handler (usually 1, can be 0 or many).
            
        Raises:
            CommandValidationError: If command is invalid.
            HandlerExecutionError: If handler fails during execution.
        """
        pass
