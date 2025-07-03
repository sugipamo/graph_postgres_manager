"""Neo4j connection management."""

import asyncio
import logging
import time
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import (
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
)

from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.connections.base import BaseConnection
from graph_postgres_manager.exceptions import Neo4jConnectionError
from graph_postgres_manager.models.types import ConnectionState

logger = logging.getLogger(__name__)


class Neo4jConnection(BaseConnection):
    """Neo4j database connection manager."""
    
    def __init__(self, config: ConnectionConfig):
        """Initialize Neo4j connection.
        
        Args:
            config: Connection configuration
        """
        super().__init__(config)
        self._driver: AsyncDriver | None = None
    
    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            self._state = ConnectionState.CONNECTING
            logger.info("Connecting to Neo4j at %s", self.config.neo4j_uri)
            
            self._driver = AsyncGraphDatabase.driver(
                self.config.neo4j_uri,
                auth=self.config.neo4j_auth,
                max_connection_pool_size=self.config.connection_pool_size,
                connection_timeout=self.config.timeout_seconds,
                keep_alive=True,
            )
            
            # Verify connection
            await self._driver.verify_connectivity()
            
            self._connection = self._driver
            self._state = ConnectionState.CONNECTED
            logger.info("Successfully connected to Neo4j")
            
        except ServiceUnavailable as e:
            self._state = ConnectionState.FAILED
            logger.error("Neo4j service unavailable: %s", e)
            raise Neo4jConnectionError(f"Failed to connect to Neo4j: {e}") from e
        except Exception as e:
            self._state = ConnectionState.FAILED
            error_msg = str(e)
            if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                logger.error("Neo4j authentication failed: %s", e)
                # Add delay to prevent rate limiting
                await asyncio.sleep(1)
            else:
                logger.error("Unexpected error connecting to Neo4j: %s", e)
            raise Neo4jConnectionError(f"Unexpected error: {e}") from e
    
    async def disconnect(self) -> None:
        """Close connection to Neo4j."""
        if self._driver:
            try:
                logger.info("Disconnecting from Neo4j")
                await self._driver.close()
                self._driver = None
                self._connection = None
                self._state = ConnectionState.CLOSED
                logger.info("Successfully disconnected from Neo4j")
            except Exception as e:
                logger.error("Error disconnecting from Neo4j: %s", e)
                self._state = ConnectionState.FAILED
    
    async def health_check(self) -> tuple[bool, float]:
        """Perform health check on Neo4j connection.
        
        Returns:
            Tuple of (is_healthy, latency_ms)
        """
        if not self._driver:
            return False, 0.0
        
        try:
            start_time = time.time()
            
            async with self._driver.session() as session:
                result = await session.run("RETURN 1 as health")
                await result.single()
            
            latency_ms = (time.time() - start_time) * 1000
            return True, latency_ms
            
        except (ServiceUnavailable, SessionExpired) as e:
            logger.warning("Neo4j health check failed: %s", e)
            if self.config.enable_auto_reconnect:
                self._state = ConnectionState.RECONNECTING
            return False, 0.0
        except Exception as e:
            logger.error("Unexpected error during Neo4j health check: %s", e)
            return False, 0.0
    
    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
        transaction=None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Target database (None for default)
            transaction: Neo4j transaction object (for transaction mode)
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            Neo4jConnectionError: If query execution fails
        """
        await self.ensure_connected()
        
        try:
            # If transaction is provided, use it directly
            if transaction:
                # Handle transaction tuple (session, tx) or direct tx object
                if isinstance(transaction, tuple):
                    session, tx = transaction
                    result = await tx.run(query, parameters or {})
                else:
                    result = await transaction.run(query, parameters or {})
                return [record.data() async for record in result]
            
            # Otherwise use a session
            async with self._driver.session(database=database) as session:
                result = await session.run(query, parameters or {})
                return [record.data() async for record in result]
                
        except (ServiceUnavailable, SessionExpired) as e:
            logger.error("Connection error during query execution: %s", e)
            if self.config.enable_auto_reconnect and not transaction:
                await self.connect_with_retry()
                # Retry once after reconnection (only if not in transaction mode)
                return await self.execute_query(query, parameters, database)
            raise Neo4jConnectionError(f"Connection error: {e}") from e
            
        except Neo4jError as e:
            logger.error("Neo4j error during query execution: %s", e)
            raise Neo4jConnectionError(f"Query execution failed: {e}") from e
    
    async def execute_transaction(
        self,
        transaction_func,
        database: str | None = None,
        **kwargs
    ) -> Any:
        """Execute a transaction function.
        
        Args:
            transaction_func: Async function to execute within transaction
            database: Target database (None for default)
            **kwargs: Additional arguments for transaction function
            
        Returns:
            Result of transaction function
            
        Raises:
            Neo4jConnectionError: If transaction fails
        """
        await self.ensure_connected()
        
        try:
            async with self._driver.session(database=database) as session:
                return await session.execute_write(
                    transaction_func,
                    **kwargs
                )
        except Exception as e:
            logger.error("Transaction execution failed: %s", e)
            raise Neo4jConnectionError(f"Transaction failed: {e}") from e
    
    async def begin_transaction(self, database: str | None = None):
        """Begin a Neo4j transaction.
        
        Args:
            database: Target database (None for default)
            
        Returns:
            Neo4j transaction object
            
        Raises:
            Neo4jConnectionError: If transaction creation fails
        """
        await self.ensure_connected()
        
        try:
            session = self._driver.session(database=database)
            transaction = await session.begin_transaction()
            return (session, transaction)  # Return both for cleanup
        except Exception as e:
            logger.error("Failed to begin transaction: %s", e)
            raise Neo4jConnectionError(f"Failed to begin transaction: {e}") from e
    
    async def batch_insert(
        self,
        query: str,
        data: list[dict[str, Any]],
        batch_size: int = 1000,
        database: str | None = None
    ) -> int:
        """Execute batch insert operation.
        
        Args:
            query: Cypher query with UNWIND (should include parameters)
            data: List of parameter dictionaries
            batch_size: Number of records per batch
            database: Target database
            
        Returns:
            Total number of inserted records
            
        Raises:
            Neo4jConnectionError: If batch insert fails
        """
        await self.ensure_connected()
        
        total_inserted = 0
        
        try:
            async with self._driver.session(database=database) as session:
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    
                    # Execute the query directly with the batch parameters
                    result = await session.run(query, batch[0])
                    summary = await result.consume()
                    total_inserted += summary.counters.nodes_created
                    
                    logger.debug(
                        "Inserted batch %d, records: %d",
                        i // batch_size + 1,
                        len(batch)
                    )
            
            logger.info("Batch insert completed. Total records: %d", total_inserted)
            return total_inserted
            
        except Exception as e:
            logger.error("Batch insert failed: %s", e)
            raise Neo4jConnectionError(f"Batch insert failed: {e}") from e
    
    @property
    def driver(self) -> AsyncDriver | None:
        """Get the underlying Neo4j driver."""
        return self._driver
    
    
    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction.
        
        Args:
            transaction: Transaction object to commit
            
        Raises:
            Neo4jConnectionError: If commit fails
        """
        if not transaction:
            return
            
        session, tx = transaction
        try:
            await tx.commit()
            await session.close()
        except Exception as e:
            logger.error("Failed to commit transaction: %s", e)
            raise Neo4jConnectionError(f"Failed to commit transaction: {e}") from e
    
    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction.
        
        Args:
            transaction: Transaction object to rollback
            
        Raises:
            Neo4jConnectionError: If rollback fails
        """
        if not transaction:
            return
            
        session, tx = transaction
        try:
            await tx.rollback()
            await session.close()
        except Exception as e:
            logger.error("Failed to rollback transaction: %s", e)
            raise Neo4jConnectionError(f"Failed to rollback transaction: {e}") from e
    
    async def prepare_transaction(self, _transaction: Any) -> None:
        """Prepare transaction for 2-phase commit (Neo4j doesn't support this natively).
        
        Args:
            transaction: Transaction object
            
        Note:
            Neo4j doesn't support 2-phase commit protocol natively.
            This is a placeholder for compatibility.
        """
        logger.warning("Neo4j doesn't support 2-phase commit protocol")
    
    async def commit_prepared(self, transaction: Any) -> None:
        """Commit a prepared transaction.
        
        Args:
            transaction: Transaction object
            
        Note:
            Since Neo4j doesn't support 2-phase commit,
            this just delegates to regular commit.
        """
        await self.commit_transaction(transaction)