"""PostgreSQL connection management."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from psycopg import AsyncConnection

try:
    from psycopg.pool import AsyncConnectionPool
except ImportError:
    from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from ..config import ConnectionConfig
from ..exceptions import PoolExhaustedError, PostgresConnectionError
from ..models.types import ConnectionState
from .base import BaseConnection

logger = logging.getLogger(__name__)


class PostgresConnection(BaseConnection):
    """PostgreSQL database connection manager."""
    
    def __init__(self, config: ConnectionConfig):
        """Initialize PostgreSQL connection.
        
        Args:
            config: Connection configuration
        """
        super().__init__(config)
        self._pool: AsyncConnectionPool | None = None
    
    async def connect(self) -> None:
        """Establish connection pool to PostgreSQL."""
        try:
            self._state = ConnectionState.CONNECTING
            logger.info("Creating PostgreSQL connection pool")
            
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
        parameters: dict[str, Any] | None = None,
        fetch_all: bool = True
    ) -> list[dict[str, Any]]:
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
                    result = await cur.fetchone()
                    return [dict(result)] if result else []
                        
        except psycopg.Error as e:
            logger.error(f"PostgreSQL query execution failed: {e}")
            raise PostgresConnectionError(f"Query execution failed: {e}") from e
    
    async def execute_many(
        self,
        query: str,
        data: list[dict[str, Any]]
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
                        param_names = re.findall(r"%\((\w+)\)s", query)
                        
                        # Convert dicts to tuples in correct order
                        tuple_data = [
                            tuple(row.get(param, None) for param in param_names)
                            for row in data
                        ]
                        
                        # Replace named placeholders with positional
                        query_positional = re.sub(r"%\(\w+\)s", "%s", query)
                        
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
    def pool(self) -> AsyncConnectionPool | None:
        """Get the underlying connection pool."""
        return self._pool
    
    @property
    def pool_status(self) -> dict[str, Any]:
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
    
    async def execute(
        self,
        query: str,
        parameters: list | dict[str, Any] | None = None,
        transaction: Any | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SQL query with optional transaction support.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            transaction: Optional transaction connection
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            PostgresConnectionError: If query execution fails
        """
        if transaction:
            # Execute within provided transaction
            try:
                conn = transaction
                async with conn.cursor() as cur:
                    await cur.execute(query, parameters or {})
                    results = await cur.fetchall()
                    return [dict(row) for row in results]
            except psycopg.Error as e:
                logger.error(f"PostgreSQL query execution failed: {e}")
                raise PostgresConnectionError(f"Query execution failed: {e}") from e
        else:
            # Use regular execute_query
            return await self.execute_query(query, parameters)
    
    async def begin_transaction(self) -> Any:
        """Begin a new transaction.
        
        Returns:
            Transaction connection object
            
        Raises:
            PostgresConnectionError: If transaction creation fails
        """
        await self.ensure_connected()
        
        try:
            conn = await self._pool.getconn()
            await conn.set_autocommit(False)
            return conn
        except Exception as e:
            logger.error(f"Failed to begin transaction: {e}")
            raise PostgresConnectionError(f"Failed to begin transaction: {e}") from e
    
    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction.
        
        Args:
            transaction: Transaction connection to commit
            
        Raises:
            PostgresConnectionError: If commit fails
        """
        if not transaction:
            return
            
        try:
            await transaction.commit()
            await self._pool.putconn(transaction)
        except Exception as e:
            logger.error(f"Failed to commit transaction: {e}")
            raise PostgresConnectionError(f"Failed to commit transaction: {e}") from e
    
    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction.
        
        Args:
            transaction: Transaction connection to rollback
            
        Raises:
            PostgresConnectionError: If rollback fails
        """
        if not transaction:
            return
            
        try:
            await transaction.rollback()
            await self._pool.putconn(transaction)
        except Exception as e:
            logger.error(f"Failed to rollback transaction: {e}")
            raise PostgresConnectionError(f"Failed to rollback transaction: {e}") from e
    
    async def prepare_transaction(self, transaction: Any) -> None:
        """Prepare transaction for 2-phase commit.
        
        Args:
            transaction: Transaction connection
            
        Note:
            PostgreSQL supports 2PC with PREPARE TRANSACTION command
        """
        if not transaction:
            return
            
        try:
            # Generate unique transaction ID
            import uuid
            xid = f"gpm_{uuid.uuid4().hex[:16]}"
            
            async with transaction.cursor() as cur:
                await cur.execute(f"PREPARE TRANSACTION '{xid}'")
            
            # Store the XID with the transaction for later
            transaction._prepared_xid = xid
        except Exception as e:
            logger.error(f"Failed to prepare transaction: {e}")
            raise PostgresConnectionError(f"Failed to prepare transaction: {e}") from e
    
    async def commit_prepared(self, transaction: Any) -> None:
        """Commit a prepared transaction.
        
        Args:
            transaction: Transaction connection with prepared XID
            
        Raises:
            PostgresConnectionError: If commit fails
        """
        if not transaction or not hasattr(transaction, "_prepared_xid"):
            return
            
        try:
            xid = transaction._prepared_xid
            # Need a new connection to commit prepared transaction
            async with self._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(f"COMMIT PREPARED '{xid}'")
            
            await self._pool.putconn(transaction)
        except Exception as e:
            logger.error(f"Failed to commit prepared transaction: {e}")
            raise PostgresConnectionError(f"Failed to commit prepared transaction: {e}") from e
    
    async def fetch_all(self, query: str, parameters: tuple | list | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query and fetch all results.
        
        Args:
            query: SQL query string
            parameters: Query parameters as tuple, list, or dict
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            PostgresConnectionError: If query execution fails
        """
        # Convert parameters to dict if needed for execute_query compatibility
        if isinstance(parameters, (tuple, list)):
            # For positional parameters, we'll use the execute method directly
            try:
                async with self.acquire_connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(query, parameters)
                        results = await cur.fetchall()
                        return [dict(row) for row in results]
            except psycopg.Error as e:
                logger.error(f"PostgreSQL query execution failed: {e}")
                raise PostgresConnectionError(f"Query execution failed: {e}") from e
        else:
            # For dict parameters or None, use execute_query
            return await self.execute_query(query, parameters, fetch_all=True)
    
    async def fetch_one(self, query: str, parameters: tuple | list | dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Execute a query and fetch one result.
        
        Args:
            query: SQL query string
            parameters: Query parameters as tuple, list, or dict
            
        Returns:
            Single result record as dictionary or None if no results
            
        Raises:
            PostgresConnectionError: If query execution fails
        """
        # Convert parameters to dict if needed for execute_query compatibility
        if isinstance(parameters, (tuple, list)):
            # For positional parameters, we'll use the execute method directly
            try:
                async with self.acquire_connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(query, parameters)
                        result = await cur.fetchone()
                        return dict(result) if result else None
            except psycopg.Error as e:
                logger.error(f"PostgreSQL query execution failed: {e}")
                raise PostgresConnectionError(f"Query execution failed: {e}") from e
        else:
            # For dict parameters or None, use execute_query
            results = await self.execute_query(query, parameters, fetch_all=False)
            return results[0] if results else None
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[AsyncConnection]:
        """Get a connection from the pool.
        
        This is an alias for acquire_connection for compatibility.
        
        Yields:
            PostgreSQL connection
            
        Raises:
            PoolExhaustedError: If pool is exhausted
            PostgresConnectionError: If connection fails
        """
        async with self.acquire_connection() as conn:
            yield conn