"""Main manager class for graph_postgres_manager."""

import asyncio
import contextlib
import logging
import time
from datetime import datetime
from typing import Any

from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.connections import Neo4jConnection, PostgresConnection
from graph_postgres_manager.exceptions import (
    DataOperationError,
    GraphPostgresManagerException,
    ValidationError,
)
from graph_postgres_manager.intent import IntentManager
from graph_postgres_manager.metadata import IndexManager, SchemaManager, StatsCollector
from graph_postgres_manager.models import EdgeType, HealthStatus
from graph_postgres_manager.search import (
    SearchFilter,
    SearchManager,
    SearchQuery,
    SearchResult,
    SearchType,
)
from graph_postgres_manager.transactions import TransactionManager

logger = logging.getLogger(__name__)


class GraphPostgresManager:
    """Unified manager for Neo4j and PostgreSQL connections."""
    
    def __init__(self, config: ConnectionConfig | None = None):
        """Initialize GraphPostgresManager.
        
        Args:
            config: Connection configuration (uses defaults if None)
        """
        self.config = config or ConnectionConfig()
        self.neo4j = Neo4jConnection(self.config)
        self.postgres = PostgresConnection(self.config)
        self._health_check_task: asyncio.Task | None = None
        self._is_initialized = False
        self._transaction_manager: TransactionManager | None = None
        self._schema_manager: SchemaManager | None = None
        self._index_manager: IndexManager | None = None
        self._stats_collector: StatsCollector | None = None
        self._search_manager: SearchManager | None = None
        self._intent_manager: IntentManager | None = None
        
        # For test compatibility
        self._neo4j_conn = self.neo4j
        self._postgres_conn = self.postgres
    
    @property
    def neo4j_connection(self) -> Neo4jConnection:
        """Get Neo4j connection (for backward compatibility)."""
        return self.neo4j
    
    @property
    def postgres_connection(self) -> PostgresConnection:
        """Get PostgreSQL connection (for backward compatibility)."""
        return self.postgres
    
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
            enable_two_phase_commit=getattr(self.config, "enable_two_phase_commit", False),
            enable_logging=getattr(self.config, "enable_transaction_logging", False)
        )
        
        # Initialize metadata managers
        self._schema_manager = SchemaManager(self.postgres)
        self._index_manager = IndexManager(self.postgres)
        self._stats_collector = StatsCollector(self.postgres)
        
        # Initialize search manager
        self._search_manager = SearchManager(
            neo4j_connection=self.neo4j,
            postgres_connection=self.postgres
        )
        
        # Initialize intent manager
        self._intent_manager = IntentManager(self.postgres)
        
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
        
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
                "Health check failed - Neo4j: %s, PostgreSQL: %s",
                neo4j_health, postgres_health
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
                logger.error("Error in health check loop: %s", e)
    
    async def execute_neo4j_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None
    ) -> list[dict[str, Any]]:
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
        parameters: dict[str, Any] | None = None,
        fetch_all: bool = True
    ) -> list[dict[str, Any]]:
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
        data: list[dict[str, Any]],
        batch_size: int = 1000,
        database: str | None = None
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
        data: list[dict[str, Any]]
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
    
    def get_config_info(self) -> dict[str, Any]:
        """Get configuration information with sensitive data masked.
        
        Returns:
            Configuration dictionary
        """
        return self.config.mask_sensitive_data()
    
    def get_connection_status(self) -> dict[str, Any]:
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
    
    def transaction(self, timeout: float | None = None):
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
    
    
    @property
    def search_manager(self) -> SearchManager:
        """Get the search manager instance.
        
        Returns:
            SearchManager instance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
        """
        if not self._is_initialized or not self._search_manager:
            raise GraphPostgresManagerException("Manager not initialized")
        return self._search_manager
    
    @property
    def intent_manager(self) -> IntentManager:
        """Get the intent manager instance.
        
        Returns:
            IntentManager instance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
        """
        if not self._is_initialized or not self._intent_manager:
            raise GraphPostgresManagerException("Manager not initialized")
        return self._intent_manager
    
    async def get_postgres_schema_info(self, schema_name: str = "public") -> dict[str, Any]:
        """Get PostgreSQL schema information.
        
        Args:
            schema_name: Name of the schema to inspect
            
        Returns:
            Dictionary with schema information
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.schema_manager.get_schema_info(schema_name)
    
    async def analyze_postgres_indexes(self, schema_name: str = "public") -> dict[str, Any]:
        """Analyze PostgreSQL index usage and provide recommendations.
        
        Args:
            schema_name: Schema to analyze
            
        Returns:
            Dictionary with index analysis results
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.index_manager.analyze_index_usage(schema_name)
    
    async def collect_postgres_stats(self, schema_name: str = "public") -> dict[str, Any]:
        """Collect PostgreSQL statistics and generate a report.
        
        Args:
            schema_name: Schema to collect stats for
            
        Returns:
            Dictionary with statistics report
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.stats_collector.generate_report(schema_name)
    
    # AST Graph Storage
    
    async def store_ast_graph(  # noqa: PLR0912
        self,
        graph_data: dict[str, Any],
        source_id: str,
        metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store AST graph data in Neo4j.
        
        Args:
            graph_data: AST graph data with 'nodes' and 'edges' keys
            source_id: Source identifier for the AST
            metadata: Optional metadata to attach to nodes
            
        Returns:
            Dictionary with import statistics
            
        Raises:
            ValidationError: If graph data is invalid
            DataOperationError: If storage fails
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        start_time = time.time()
        
        # Validate graph data
        self._validate_ast_graph(graph_data)
        
        try:
            # Process nodes in batches
            nodes = graph_data["nodes"]
            edges = graph_data["edges"]
            
            total_nodes = 0
            total_edges = 0
            
            # Batch size for optimal performance
            batch_size = 1000
            
            # Create nodes in batches
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i:i + batch_size]
                node_data = []
                
                for node in batch:
                    # Ensure source_id is set
                    node_props = {
                        "id": node["id"],
                        "node_type": node["node_type"],
                        "source_id": source_id
                    }
                    
                    # Add optional fields
                    if "value" in node and node["value"] is not None:
                        node_props["value"] = node["value"]
                    if "lineno" in node and node["lineno"] is not None:
                        node_props["lineno"] = node["lineno"]
                    
                    # Add metadata if provided
                    if metadata:
                        node_props.update(metadata)
                    
                    node_data.append({"props": node_props})
                
                # Use MERGE to handle duplicates gracefully
                query = """
                UNWIND $nodes AS node
                MERGE (n:ASTNode {id: node.props.id, source_id: node.props.source_id})
                SET n += node.props
                RETURN COUNT(n) AS created
                """
                
                result = await self._neo4j_conn.execute_query(
                    query,
                    {"nodes": node_data}
                )
                
                if result and len(result) > 0:
                    total_nodes += result[0].get("created", 0)
            
            # Create edges in batches
            for i in range(0, len(edges), batch_size):
                batch = edges[i:i + batch_size]
                edge_data = []
                
                for edge in batch:
                    edge_data.append({
                        "source": edge["source"],
                        "target": edge["target"],
                        "type": edge["type"]
                    })
                
                # Create relationships based on type
                query = """
                UNWIND $edges AS edge
                MATCH (s:ASTNode {id: edge.source, source_id: $source_id})
                MATCH (t:ASTNode {id: edge.target, source_id: $source_id})
                WITH s, t, edge
                CALL apoc.create.relationship(s, edge.type, {}, t) YIELD rel
                RETURN COUNT(rel) AS created
                """
                
                # If APOC is not available, fall back to dynamic Cypher
                try:
                    result = await self._neo4j_conn.execute_query(
                        query,
                        {"edges": edge_data, "source_id": source_id}
                    )
                except Exception:
                    # Fallback for each edge type
                    for edge_type in ["CHILD", "NEXT", "DEPENDS_ON"]:
                        type_edges = [e for e in edge_data if e["type"] == edge_type]
                        if type_edges:
                            query = f"""
                            UNWIND $edges AS edge
                            MATCH (s:ASTNode {{id: edge.source, source_id: $source_id}})
                            MATCH (t:ASTNode {{id: edge.target, source_id: $source_id}})
                            MERGE (s)-[:{edge_type}]->(t)
                            RETURN COUNT(*) AS created
                            """
                            result = await self._neo4j_conn.execute_query(
                                query,
                                {"edges": type_edges, "source_id": source_id}
                            )
                            if result and len(result) > 0:
                                total_edges += result[0].get("created", 0)
                else:
                    if result and len(result) > 0:
                        total_edges += result[0].get("created", 0)
            
            # Create indexes if they don't exist (skip for now to debug)
            # await self._ensure_ast_indexes()
            
            # Calculate performance metrics
            elapsed_time = time.time() - start_time
            nodes_per_second = total_nodes / elapsed_time if elapsed_time > 0 else 0
            
            return {
                "created_nodes": total_nodes,
                "created_edges": total_edges,
                "import_time_ms": int(elapsed_time * 1000),
                "nodes_per_second": int(nodes_per_second)
            }
            
        except Exception as e:
            logger.error("Failed to store AST graph: %s", e)
            raise DataOperationError(f"Failed to store AST graph: {e}") from e
    
    def _validate_ast_graph(self, graph_data: dict[str, Any]) -> None:  # noqa: PLR0912
        """Validate AST graph data structure.
        
        Args:
            graph_data: Graph data to validate
            
        Raises:
            ValidationError: If validation fails
        """
        # Check required fields
        if "nodes" not in graph_data:
            raise ValidationError("Missing required field 'nodes' in graph data")
        
        if "edges" not in graph_data:
            raise ValidationError("Missing required field 'edges' in graph data")
        
        if not isinstance(graph_data["nodes"], list):
            raise ValidationError("Field 'nodes' must be a list")
        
        if not isinstance(graph_data["edges"], list):
            raise ValidationError("Field 'edges' must be a list")
        
        # Validate nodes
        node_ids = set()
        for i, node in enumerate(graph_data["nodes"]):
            if not isinstance(node, dict):
                raise ValidationError(f"Node at index {i} must be a dictionary")
            
            # Check required node fields
            if "id" not in node:
                raise ValidationError(f"Node at index {i}: Missing required field 'id'")
            
            if "node_type" not in node:
                raise ValidationError(f"Node at index {i}: Missing required field 'node_type'")
            
            # Track node IDs for edge validation
            node_ids.add(node["id"])
        
        # Validate edges
        valid_edge_types = {e.value for e in EdgeType}
        for i, edge in enumerate(graph_data["edges"]):
            if not isinstance(edge, dict):
                raise ValidationError(f"Edge at index {i} must be a dictionary")
            
            # Check required edge fields
            if "source" not in edge:
                raise ValidationError(f"Edge at index {i}: Missing required field 'source'")
            
            if "target" not in edge:
                raise ValidationError(f"Edge at index {i}: Missing required field 'target'")
            
            if "type" not in edge:
                raise ValidationError(f"Edge at index {i}: Missing required field 'type'")
            
            # Validate edge type
            if edge["type"] not in valid_edge_types:
                raise ValidationError(
                    f"Edge at index {i}: Invalid edge type '{edge['type']}'. "
                    f"Must be one of: {', '.join(valid_edge_types)}"
                )
            
            # Validate edge references exist
            if edge["source"] not in node_ids:
                raise ValidationError(
                    f"Edge at index {i}: Source node '{edge['source']}' not found in nodes"
                )
            
            if edge["target"] not in node_ids:
                raise ValidationError(
                    f"Edge at index {i}: Target node '{edge['target']}' not found in nodes"
                )
    
    async def _ensure_ast_indexes(self) -> None:
        """Ensure required indexes exist for AST nodes."""
        # Try to create indexes, ignore errors if they already exist
        indexes = [
            "CREATE INDEX astnode_id IF NOT EXISTS FOR (n:ASTNode) ON (n.id)",
            "CREATE INDEX astnode_source_id IF NOT EXISTS FOR (n:ASTNode) ON (n.source_id)",
            "CREATE INDEX astnode_node_type IF NOT EXISTS FOR (n:ASTNode) ON (n.node_type)"
        ]
        
        for query in indexes:
            with contextlib.suppress(Exception):
                await self._neo4j_conn.execute_query(query)
    
    
    # Unified Search
    
    async def search_unified(
        self,
        query: str | SearchQuery,
        include_graph: bool = True,
        include_text: bool = True,
        filters: dict[str, Any] | None = None,
        max_results: int = 100
    ) -> list[SearchResult]:
        """Perform unified search across graph and text data sources.
        
        This method integrates graph search (Neo4j) and full-text search (PostgreSQL)
        to provide comprehensive search results.
        
        Args:
            query: Search query string or SearchQuery object
            include_graph: Include Neo4j graph search
            include_text: Include PostgreSQL full-text search
            filters: Optional filters (node_types, source_ids, etc.)
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects ranked by relevance
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
            ValidationError: If inputs are invalid
            DataOperationError: If search fails
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        # Build SearchQuery if string provided
        if isinstance(query, str):
            
            # Determine search types based on parameters
            search_types = []
            if include_graph and include_text:
                search_types = [SearchType.UNIFIED]
            else:
                if include_graph:
                    search_types.append(SearchType.GRAPH)
                if include_text:
                    search_types.append(SearchType.TEXT)
            
            # Build filter from dict
            filter_obj = SearchFilter(max_results=max_results)
            if filters:
                if "node_types" in filters:
                    filter_obj.node_types = filters["node_types"]
                if "source_ids" in filters:
                    filter_obj.source_ids = filters["source_ids"]
                if "file_patterns" in filters:
                    filter_obj.file_patterns = filters["file_patterns"]
                if "min_confidence" in filters:
                    filter_obj.min_confidence = filters["min_confidence"]
            
            query_obj = SearchQuery(
                query=query,
                search_types=search_types,
                filters=filter_obj
            )
        else:
            query_obj = query
        
        # Execute search
        return await self.search_manager.search(query_obj)
    
    # Intent Management
    
    async def link_intent_to_ast(
        self,
        intent_id: str,
        ast_node_ids: list[str],
        source_id: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        intent_vector: list[float] | None = None
    ) -> dict[str, Any]:
        """Link intent data to AST nodes.
        
        This method creates mappings between intent data (managed by intent_store)
        and AST nodes (stored in Neo4j). It supports vector storage for similarity search.
        
        Args:
            intent_id: Intent identifier from intent_store
            ast_node_ids: List of AST node IDs to link
            source_id: Source code identifier
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata
            intent_vector: Optional 768-dimensional vector representation
            
        Returns:
            Dictionary with linking results:
            - intent_id: The intent ID
            - mapped_ast_nodes: Number of nodes linked
            - mapping_ids: List of created mapping IDs
            - vector_stored: Whether vector was stored
            
        Raises:
            GraphPostgresManagerException: If manager not initialized
            ValidationError: If parameters are invalid
            DataOperationError: If the operation fails
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.link_intent_to_ast(
            intent_id=intent_id,
            ast_node_ids=ast_node_ids,
            source_id=source_id,
            confidence=confidence,
            metadata=metadata,
            intent_vector=intent_vector
        )
    
    async def get_ast_nodes_by_intent(
        self,
        intent_id: str,
        min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """Get AST nodes linked to an intent.
        
        Args:
            intent_id: Intent identifier
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of AST node information with confidence scores
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.get_ast_nodes_by_intent(intent_id, min_confidence)
    
    async def get_intents_for_ast(
        self,
        ast_node_id: str,
        min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """Get intents linked to an AST node.
        
        Args:
            ast_node_id: AST node identifier
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of intent information with confidence scores
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.get_intents_for_ast(ast_node_id, min_confidence)
    
    async def search_ast_by_intent_vector(
        self,
        intent_vector: list[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Search for AST nodes by intent vector similarity.
        
        Uses pgvector to find AST nodes linked to similar intents.
        
        Args:
            intent_vector: 768-dimensional search vector
            limit: Maximum number of results
            threshold: Similarity threshold (0.0-1.0)
            
        Returns:
            List of matching AST nodes with similarity scores
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.search_ast_by_intent_vector(
            intent_vector=intent_vector,
            limit=limit,
            threshold=threshold
        )
    
    async def update_intent_confidence(
        self,
        intent_id: str,
        ast_node_id: str,
        new_confidence: float
    ) -> bool:
        """Update the confidence score for an intent-AST mapping.
        
        Args:
            intent_id: Intent identifier
            ast_node_id: AST node identifier
            new_confidence: New confidence score (0.0-1.0)
            
        Returns:
            True if updated successfully
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.update_intent_confidence(
            intent_id=intent_id,
            ast_node_id=ast_node_id,
            new_confidence=new_confidence
        )
    
    async def remove_intent_mapping(
        self,
        intent_id: str,
        ast_node_id: str | None = None
    ) -> int:
        """Remove intent-AST mappings.
        
        Args:
            intent_id: Intent identifier
            ast_node_id: Optional specific AST node to unlink
            
        Returns:
            Number of mappings removed
        """
        if not self._is_initialized:
            raise GraphPostgresManagerException("Manager not initialized")
        
        return await self.intent_manager.remove_intent_mapping(
            intent_id=intent_id,
            ast_node_id=ast_node_id
        )