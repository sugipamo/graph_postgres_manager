"""Neo4j connection management."""

import asyncio
import logging
import time
from typing import Optional, Any, Dict, List

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import (
    ServiceUnavailable,
    SessionExpired,
    Neo4jError,
)

from .base import BaseConnection
from ..config import ConnectionConfig
from ..exceptions import Neo4jConnectionError
from ..models.types import ConnectionState


logger = logging.getLogger(__name__)


class Neo4jConnection(BaseConnection):
    """Neo4j database connection manager."""
    
    def __init__(self, config: ConnectionConfig):
        """Initialize Neo4j connection.
        
        Args:
            config: Connection configuration
        """
        super().__init__(config)
        self._driver: Optional[AsyncDriver] = None
    
    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            self._state = ConnectionState.CONNECTING
            logger.info(f"Connecting to Neo4j at {self.config.neo4j_uri}")
            
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
            logger.error(f"Neo4j service unavailable: {e}")
            raise Neo4jConnectionError(f"Failed to connect to Neo4j: {e}") from e
        except Exception as e:
            self._state = ConnectionState.FAILED
            logger.error(f"Unexpected error connecting to Neo4j: {e}")
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
                logger.error(f"Error disconnecting from Neo4j: {e}")
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
            logger.warning(f"Neo4j health check failed: {e}")
            if self.config.enable_auto_reconnect:
                self._state = ConnectionState.RECONNECTING
            return False, 0.0
        except Exception as e:
            logger.error(f"Unexpected error during Neo4j health check: {e}")
            return False, 0.0
    
    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Target database (None for default)
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            Neo4jConnectionError: If query execution fails
        """
        await self.ensure_connected()
        
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, parameters or {})
                records = [record.data() async for record in result]
                return records
                
        except (ServiceUnavailable, SessionExpired) as e:
            logger.error(f"Connection error during query execution: {e}")
            if self.config.enable_auto_reconnect:
                await self.connect_with_retry()
                # Retry once after reconnection
                return await self.execute_query(query, parameters, database)
            raise Neo4jConnectionError(f"Connection error: {e}") from e
            
        except Neo4jError as e:
            logger.error(f"Neo4j error during query execution: {e}")
            raise Neo4jConnectionError(f"Query execution failed: {e}") from e
    
    async def execute_transaction(
        self,
        transaction_func,
        database: Optional[str] = None,
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
            logger.error(f"Transaction execution failed: {e}")
            raise Neo4jConnectionError(f"Transaction failed: {e}") from e
    
    async def batch_insert(
        self,
        query: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000,
        database: Optional[str] = None
    ) -> int:
        """Execute batch insert operation.
        
        Args:
            query: Cypher query with UNWIND
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
                    
                    result = await session.run(
                        f"UNWIND $batch AS row {query}",
                        {"batch": batch}
                    )
                    summary = await result.consume()
                    total_inserted += summary.counters.nodes_created
                    
                    logger.debug(
                        f"Inserted batch {i // batch_size + 1}, "
                        f"records: {len(batch)}"
                    )
            
            logger.info(f"Batch insert completed. Total records: {total_inserted}")
            return total_inserted
            
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            raise Neo4jConnectionError(f"Batch insert failed: {e}") from e
    
    @property
    def driver(self) -> Optional[AsyncDriver]:
        """Get the underlying Neo4j driver."""
        return self._driver