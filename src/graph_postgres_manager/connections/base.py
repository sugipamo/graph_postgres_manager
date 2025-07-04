"""Base connection class for database connections."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.exceptions import (
    GraphConnectionError,
    OperationTimeoutError,
    RetryExhaustedError,
)
from graph_postgres_manager.models.types import ConnectionState

logger = logging.getLogger(__name__)


class BaseConnection(ABC):
    """Abstract base class for database connections."""
    
    def __init__(self, config: ConnectionConfig):
        """Initialize base connection.
        
        Args:
            config: Connection configuration
        """
        self.config = config
        self._state = ConnectionState.DISCONNECTED
        self._connection: Any | None = None
        self._last_health_check: datetime | None = None
        self._retry_count = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_last_failure: datetime | None = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._state == ConnectionState.CONNECTED
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the database."""
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the database."""
    
    @abstractmethod
    async def health_check(self) -> tuple[bool, float]:
        """Perform health check on the connection.
        
        Returns:
            Tuple of (is_healthy, latency_ms)
        """
    
    async def ensure_connected(self) -> None:
        """Ensure connection is established, reconnecting if necessary."""
        if not self.is_connected:
            await self.connect_with_retry()
    
    async def connect_with_retry(self) -> None:
        """Connect with retry logic."""
        last_error: Exception | None = None
        
        for attempt in range(self.config.max_retry_attempts + 1):
            try:
                if self._circuit_breaker_open:
                    if not self._should_attempt_reconnect():
                        raise GraphConnectionError("Circuit breaker is open")
                    self._circuit_breaker_open = False
                
                await self.connect()
                self._retry_count = 0
                return
                
            except Exception as e:
                last_error = e
                self._retry_count = attempt + 1
                
                if attempt < self.config.max_retry_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        "Connection attempt %d failed: %s. Retrying in %ds...",
                        attempt + 1, e, delay
                    )
                    await asyncio.sleep(delay)
                else:
                    self._open_circuit_breaker()
        
        raise RetryExhaustedError(
            f"Failed to connect after {self.config.max_retry_attempts + 1} attempts",
            last_error
        )
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay.
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        return min(
            self.config.retry_backoff_factor ** attempt,
            self.config.retry_max_delay
        )
    
    def _open_circuit_breaker(self) -> None:
        """Open circuit breaker after consecutive failures."""
        self._circuit_breaker_open = True
        self._circuit_breaker_last_failure = datetime.now()
        logger.error("Circuit breaker opened due to consecutive failures")
    
    def _should_attempt_reconnect(self) -> bool:
        """Check if we should attempt reconnection based on circuit breaker state.
        
        Returns:
            True if reconnection should be attempted
        """
        if not self._circuit_breaker_open:
            return True
        
        if self._circuit_breaker_last_failure is None:
            return True
        
        elapsed = (datetime.now() - self._circuit_breaker_last_failure).total_seconds()
        return elapsed >= self.config.retry_max_delay
    
    async def execute_with_timeout(
        self,
        coro,
        timeout: int | None = None
    ) -> Any:
        """Execute coroutine with timeout.
        
        Args:
            coro: Coroutine to execute
            timeout: Timeout in seconds (uses config default if None)
            
        Returns:
            Result of coroutine execution
            
        Raises:
            CustomTimeoutError: If execution times out
        """
        timeout = timeout or self.config.timeout_seconds
        
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError as e:
            raise OperationTimeoutError(f"Operation timed out after {timeout} seconds") from e
    
    @asynccontextmanager
    async def acquire_connection(self) -> AsyncIterator[Any]:
        """Acquire connection with automatic management.
        
        Yields:
            Connection object
        """
        async with self._lock:
            await self.ensure_connected()
            yield self._connection
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect_with_retry()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()