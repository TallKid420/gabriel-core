"""Execution scheduler: Manages execution lifecycle."""
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from gabriel.runtime.execution import Execution, ExecutionState
from gabriel.runtime.exceptions import SchedulerError


class Scheduler(ABC):
    """Abstract scheduler for managing executions.
    
    A scheduler implements the execution pipeline:
    - command → handler → event → execution → schedule(execution)
    
    Different schedulers can implement different execution models:
    - Immediate/synchronous execution
    - Async/background execution
    - Distributed/remote execution
    - Rate-limited execution
    """

    @abstractmethod
    async def schedule(self, execution: Execution) -> Execution:
        """Schedule an execution to run.
        
        Args:
            execution: The execution to schedule (in PENDING state).
            
        Returns:
            Execution: The scheduled execution (may be RUNNING or PENDING).
            
        Raises:
            SchedulerError: If scheduling fails.
        """
        ...

    @abstractmethod
    async def cancel(self, execution_id: UUID) -> None:
        """Cancel a running execution.
        
        Args:
            execution_id: The execution to cancel.
            
        Raises:
            SchedulerError: If cancellation fails or execution not found.
        """
        ...

    @abstractmethod
    async def get_execution(self, execution_id: UUID) -> Execution | None:
        """Get an execution by ID.
        
        Args:
            execution_id: The execution ID to retrieve.
            
        Returns:
            Execution | None: The execution or None if not found.
        """
        ...

    @abstractmethod
    async def list_executions(
        self,
        organization_id: str,
        state: ExecutionState | None = None,
    ) -> list[Execution]:
        """List executions in an organization.
        
        Args:
            organization_id: The organization to list executions for.
            state: Optional state filter.
            
        Returns:
            list[Execution]: List of matching executions.
        """
        ...

    async def wait_for_completion(
        self,
        execution_id: UUID,
        timeout_seconds: float | None = None,
    ) -> Execution:
        """Wait for an execution to complete.
        
        Args:
            execution_id: The execution to wait for.
            timeout_seconds: Max time to wait (None = infinite).
            
        Returns:
            Execution: The completed execution.
            
        Raises:
            SchedulerError: If timeout or execution not found.
        """
        import asyncio
        import time

        start_time = time.time()
        poll_interval = 0.1

        while True:
            execution = await self.get_execution(execution_id)
            if execution is None:
                raise SchedulerError(f"Execution {execution_id} not found")

            if execution.is_terminal():
                return execution

            if timeout_seconds is not None:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    raise SchedulerError(
                        f"Timeout waiting for execution {execution_id}"
                    )

            await asyncio.sleep(poll_interval)
