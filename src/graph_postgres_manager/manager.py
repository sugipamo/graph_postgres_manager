"""Main manager class for graph_postgres_manager."""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from .config import ConnectionConfig
from .connections import Neo4jConnection, PostgresConnection
from .exceptions import GraphPostgresManagerException, HealthCheckError
from .models import HealthStatus
from .transactions import TransactionManager
from .metadata import SchemaManager, IndexManager, StatsCollector


logger = logging.getLogger(__name__)


class GraphPostgresManager:
    """Unified manager for Neo4j and PostgreSQL connections."""
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        """Initialize GraphPostgresManager.
        
        Args:
            config: Connection configuration (uses defaults if None)
        """
        self.config = config or ConnectionConfig()
        self.neo4j = Neo4jConnection(self.config)
        self.postgres = PostgresConnection(self.config)
        self._health_check_task: Optional[asyncio.Task] = None
        self._is_initialized = False
        self._transaction_manager: Optional[TransactionManager] = None
        self._schema_manager: Optional[SchemaManager] = None
        self._index_manager: Optional[IndexManager] = None
        self._stats_collector: Optional[StatsCollector] = None
    
    async def initialize(self) -> None:
        """Initialize all connections."""
        if self._is_initialized:
            logger.warning("Manager already initialized")
            return
        
        logger.info("Initializing GraphPostgresManager")
        
        # Connect to both databases
        await asyncio.gather(
            self.neo4j.connect_with_retry(),
            self.postgres.connect_with_retry(),
        )
        
        # Start health check task if enabled
        if self.config.health_check_interval > 0:
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
        
        # Initialize transaction manager
        self._transaction_manager = TransactionManager(
            neo4j_connection=self.neo4j,
            postgres_connection=self.postgres,
            enable_two_phase_commit=getattr(self.config, 'enable_two_phase_commit', False),
            enable_logging=getattr(self.config, 'enable_transaction_logging', False)
        )
        
        # Initialize metadata managers
        self._schema_manager = SchemaManager(self.postgres)
        self._index_manager = IndexManager(self.postgres)
        self._stats_collector = StatsCollector(self.postgres)
        
        # Initialize metadata schema
        await self._schema_manager.initialize_metadata_schema()
        
        self._is_initialized = True
        logger.info("GraphPostgresManager initialized successfully")
    
    async def close(self) -> None:
        """Close all connections and clean up resources."""
        logger.info("Closing GraphPostgresManager")
        
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from databases
        await asyncio.gather(
            self.neo4j.disconnect(),
            self.postgres.disconnect(),
            return_exceptions=True
        )
        
        self._is_initialized = False
        logger.info("GraphPostgresManager closed")
    
    async def health_check(self) -> HealthStatus:
        """Perform health check on all connections.
        
        Returns:
            HealthStatus object
        """
        neo4j_health, neo4j_latency = await self.neo4j.health_check()
        postgres_health, postgres_latency = await self.postgres.health_check()
        
        status = HealthStatus(
            neo4j_connected=neo4j_health,
            postgres_connected=postgres_health,
            neo4j_latency_ms=neo4j_latency,
            postgres_latency_ms=postgres_latency,
            timestamp=datetime.now(),
            neo4j_error=None if neo4j_health else "Connection failed",
            postgres_error=None if postgres_health else "Connection failed",
        )
        
        if not status.is_healthy:
            logger.warning(
                f"Health check failed - Neo4j: {neo4j_health}, "
                f"PostgreSQL: {postgres_health}"
            )
        
        return status
    
    async def _health_check_loop(self) -> None:
        """Background task for periodic health checks."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                status = await self.health_check()
                
                if not status.is_healthy:
                    logger.error("Health check failed, attempting reconnection")
                    
                    # Attempt to reconnect failed connections
                    tasks = []
                    if not status.neo4j_connected:
                        tasks.append(self.neo4j.connect_with_retry())
                    if not status.postgres_connected:
                        tasks.append(self.postgres.connect_with_retry())
                    
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
    async def execute_neo4j_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute Cypher query on Neo4j.
        
        Args:
            query: Cypher query
            parameters: Query parameters
            database: Target database
            
        Returns:
            Query results
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.neo4j.execute_query(query, parameters, database)
    
    async def execute_postgres_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        fetch_all: bool = True
    ) -> List[Dict[str, Any]]:
        """Execute SQL query on PostgreSQL.
        
        Args:
            query: SQL query
            parameters: Query parameters
            fetch_all: Whether to fetch all results
            
        Returns:
            Query results
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.postgres.execute_query(query, parameters, fetch_all)
    
    async def batch_insert_neo4j(
        self,
        query: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000,
        database: Optional[str] = None
    ) -> int:
        """Batch insert data into Neo4j.
        
        Args:
            query: Cypher query with UNWIND
            data: List of parameter dictionaries
            batch_size: Records per batch
            database: Target database
            
        Returns:
            Number of inserted records
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.neo4j.batch_insert(query, data, batch_size, database)
    
    async def batch_insert_postgres(
        self,
        query: str,
        data: List[Dict[str, Any]]
    ) -> int:
        """Batch insert data into PostgreSQL.
        
        Args:
            query: SQL query
            data: List of parameter dictionaries
            
        Returns:
            Number of affected rows
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.postgres.execute_many(query, data)
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get configuration information with sensitive data masked.
        
        Returns:
            Configuration dictionary
        """
        return self.config.mask_sensitive_data()
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status.
        
        Returns:
            Status dictionary
        """
        return {
            "initialized": self._is_initialized,
            "neo4j": {
                "state": self.neo4j.state.value,
                "connected": self.neo4j.is_connected,
            },
            "postgres": {
                "state": self.postgres.state.value,
                "connected": self.postgres.is_connected,
                "pool_status": self.postgres.pool_status,
            },
        }
    
    def transaction(self, timeout: Optional[float] = None):
        """Create a transaction context.
        
        Args:
            timeout: Optional timeout for the transaction
            
        Returns:
            TransactionContext for managing distributed transactions
            
        Example:
            async with manager.transaction() as tx:
                await tx.neo4j_execute("CREATE (n:Node {id: $id})", {"id": 1})
                await tx.postgres_execute("INSERT INTO nodes (id) VALUES ($1)", [1])
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        if not self._transaction_manager:
            raise GraphPostgresManagerException("Transaction manager not available")
        
        return self._transaction_manager.transaction(timeout)
    
    # Metadata Management APIs
    
    @property
    def schema_manager(self) -> SchemaManager:
        """Get the schema manager instance.
        
        Returns:
            SchemaManager instance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
        """
        if not self._is_initialized or not self._schema_manager:
            raise GraphPostgresManagerException("Manager not initialized")
        return self._schema_manager
    
    @property
    def index_manager(self) -> IndexManager:
        """Get the index manager instance.
        
        Returns:
            IndexManager instance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
        """
        if not self._is_initialized or not self._index_manager:
            raise GraphPostgresManagerException("Manager not initialized")
        return self._index_manager
    
    @property
    def stats_collector(self) -> StatsCollector:
        """Get the stats collector instance.
        
        Returns:
            StatsCollector instance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
        """
        if not self._is_initialized or not self._stats_collector:
            raise GraphPostgresManagerException("Manager not initialized")
        return self._stats_collector
    
    async def get_postgres_schema_info(self, schema_name: str = 'public') -> Dict[str, Any]:
        """Get PostgreSQL schema information.
        
        Args:
            schema_name: Name of the schema to inspect
            
        Returns:
            Dictionary with schema information
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.schema_manager.get_schema_info(schema_name)
    
    async def analyze_postgres_indexes(self, schema_name: str = 'public') -> Dict[str, Any]:
        """Analyze PostgreSQL index usage and provide recommendations.
        
        Args:
            schema_name: Schema to analyze
            
        Returns:
            Dictionary with index analysis results
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.index_manager.analyze_index_usage(schema_name)
    
    async def collect_postgres_stats(self, schema_name: str = 'public') -> Dict[str, Any]:
        """Collect PostgreSQL statistics and generate a report.
        
        Args:
            schema_name: Schema to collect stats for
            
        Returns:
            Dictionary with statistics report
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.stats_collector.generate_report(schema_name)