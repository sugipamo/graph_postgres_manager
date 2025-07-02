"""PostgreSQL connection management."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict, List, AsyncIterator

import psycopg
from psycopg import AsyncConnection
from psycopg.pool import AsyncConnectionPool
from psycopg.rows import dict_row

from .base import BaseConnection
from ..config import ConnectionConfig
from ..exceptions import PostgresConnectionError, PoolExhaustedError
from ..models.types import ConnectionState


logger = logging.getLogger(__name__)


class PostgresConnection(BaseConnection):
    """PostgreSQL database connection manager."""
    
    def __init__(self, config: ConnectionConfig):
        """Initialize PostgreSQL connection.
        
        Args:
            config: Connection configuration
        """
        super().__init__(config)
        self._pool: Optional[AsyncConnectionPool] = None
    
    async def connect(self) -> None:
        """Establish connection pool to PostgreSQL."""
        try:
            self._state = ConnectionState.CONNECTING
            logger.info(f"Creating PostgreSQL connection pool")
            
            # Create connection pool
            self._pool = AsyncConnectionPool(
                conninfo=self.config.postgres_dsn,
                min_size=1,
                max_size=self.config.connection_pool_size,
                timeout=self.config.timeout_seconds,
                kwargs={
                    "row_factory": dict_row,
                    "autocommit": False,
                }
            )
            
            # Initialize pool
            await self._pool.open()
            await self._pool.wait()
            
            self._connection = self._pool
            self._state = ConnectionState.CONNECTED
            logger.info("Successfully created PostgreSQL connection pool")
            
        except psycopg.OperationalError as e:
            self._state = ConnectionState.FAILED
            logger.error(f"PostgreSQL connection failed: {e}")
            raise PostgresConnectionError(f"Failed to connect to PostgreSQL: {e}") from e
        except Exception as e:
            self._state = ConnectionState.FAILED
            logger.error(f"Unexpected error connecting to PostgreSQL: {e}")
            raise PostgresConnectionError(f"Unexpected error: {e}") from e
    
    async def disconnect(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            try:
                logger.info("Closing PostgreSQL connection pool")
                await self._pool.close()
                self._pool = None
                self._connection = None
                self._state = ConnectionState.CLOSED
                logger.info("Successfully closed PostgreSQL connection pool")
            except Exception as e:
                logger.error(f"Error closing PostgreSQL pool: {e}")
                self._state = ConnectionState.FAILED
    
    async def health_check(self) -> tuple[bool, float]:
        """Perform health check on PostgreSQL connection.
        
        Returns:
            Tuple of (is_healthy, latency_ms)
        """
        if not self._pool:
            return False, 0.0
        
        try:
            start_time = time.time()
            
            async with self._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1 as health")
                    await cur.fetchone()
            
            latency_ms = (time.time() - start_time) * 1000
            return True, latency_ms
            
        except psycopg.OperationalError as e:
            logger.warning(f"PostgreSQL health check failed: {e}")
            if self.config.enable_auto_reconnect:
                self._state = ConnectionState.RECONNECTING
            return False, 0.0
        except Exception as e:
            logger.error(f"Unexpected error during PostgreSQL health check: {e}")
            return False, 0.0
    
    @asynccontextmanager
    async def acquire_connection(self) -> AsyncIterator[AsyncConnection]:
        """Acquire a connection from the pool.
        
        Yields:
            PostgreSQL connection
            
        Raises:
            PoolExhaustedError: If pool is exhausted
            PostgresConnectionError: If connection fails
        """
        await self.ensure_connected()
        
        try:
            async with self._pool.connection() as conn:
                yield conn
        except psycopg.PoolTimeout:
            raise PoolExhaustedError(
                f"Connection pool exhausted (timeout: {self.config.timeout_seconds}s)"
            )
        except Exception as e:
            logger.error(f"Error acquiring connection: {e}")
            raise PostgresConnectionError(f"Failed to acquire connection: {e}") from e
    
    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        fetch_all: bool = True
    ) -> List[Dict[str, Any]]:
        """Execute a SQL query.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            fetch_all: Whether to fetch all results
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            PostgresConnectionError: If query execution fails
        """
        try:
            async with self.acquire_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, parameters or {})
                    
                    if fetch_all:
                        results = await cur.fetchall()
                        return [dict(row) for row in results]
                    else:
                        result = await cur.fetchone()
                        return [dict(result)] if result else []
                        
        except psycopg.Error as e:
            logger.error(f"PostgreSQL query execution failed: {e}")
            raise PostgresConnectionError(f"Query execution failed: {e}") from e
    
    async def execute_many(
        self,
        query: str,
        data: List[Dict[str, Any]]
    ) -> int:
        """Execute query for multiple parameter sets.
        
        Args:
            query: SQL query string
            data: List of parameter dictionaries
            
        Returns:
            Number of affected rows
            
        Raises:
            PostgresConnectionError: If execution fails
        """
        try:
            async with self.acquire_connection() as conn:
                async with conn.cursor() as cur:
                    # Convert dict parameters to tuples for executemany
                    if data and isinstance(data[0], dict):
                        # Extract parameter names from query
                        import re
                        param_names = re.findall(r'%\((\w+)\)s', query)
                        
                        # Convert dicts to tuples in correct order
                        tuple_data = [
                            tuple(row.get(param, None) for param in param_names)
                            for row in data
                        ]
                        
                        # Replace named placeholders with positional
                        query_positional = re.sub(r'%\(\w+\)s', '%s', query)
                        
                        await cur.executemany(query_positional, tuple_data)
                    else:
                        await cur.executemany(query, data)
                    
                    return cur.rowcount or 0
                    
        except psycopg.Error as e:
            logger.error(f"PostgreSQL executemany failed: {e}")
            raise PostgresConnectionError(f"Batch execution failed: {e}") from e
    
    async def execute_transaction(
        self,
        transaction_func,
        **kwargs
    ) -> Any:
        """Execute a function within a transaction.
        
        Args:
            transaction_func: Async function to execute
            **kwargs: Arguments for transaction function
            
        Returns:
            Result of transaction function
            
        Raises:
            PostgresConnectionError: If transaction fails
        """
        try:
            async with self.acquire_connection() as conn:
                async with conn.transaction():
                    return await transaction_func(conn, **kwargs)
                    
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            raise PostgresConnectionError(f"Transaction failed: {e}") from e
    
    async def create_table_if_not_exists(
        self,
        table_name: str,
        schema: str
    ) -> None:
        """Create table if it doesn't exist.
        
        Args:
            table_name: Name of the table
            schema: CREATE TABLE schema definition
            
        Raises:
            PostgresConnectionError: If table creation fails
        """
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
        
        try:
            async with self.acquire_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    
            logger.info(f"Ensured table {table_name} exists")
            
        except psycopg.Error as e:
            logger.error(f"Table creation failed: {e}")
            raise PostgresConnectionError(f"Failed to create table: {e}") from e
    
    @property
    def pool(self) -> Optional[AsyncConnectionPool]:
        """Get the underlying connection pool."""
        return self._pool
    
    @property
    def pool_status(self) -> Dict[str, Any]:
        """Get connection pool status.
        
        Returns:
            Dictionary with pool statistics
        """
        if not self._pool:
            return {"status": "not_initialized"}
        
        return {
            "status": "active",
            "min_size": self._pool.min_size,
            "max_size": self._pool.max_size,
            "current_size": len(self._pool._pool),
            "available": len([c for c in self._pool._pool if c.available]),
            "in_use": len([c for c in self._pool._pool if not c.available]),
        }