"""Mock implementation of GraphPostgresManager.

This module provides a complete mock implementation of GraphPostgresManager
that uses in-memory storage and requires no external dependencies.
"""

from typing import Dict, List, Any, Optional, Union
import asyncio
import uuid
import time
from datetime import datetime
from contextlib import asynccontextmanager

from .data_store import InMemoryDataStore
from .connections import MockNeo4jConnection, MockPostgresConnection, ConnectionState
from .transactions import MockTransactionManager


class MockHealthStatus:
    """Mock health status data class."""
    
    def __init__(
        self,
        neo4j_connected: bool,
        postgres_connected: bool,
        neo4j_latency_ms: float,
        postgres_latency_ms: float,
        timestamp: datetime,
        neo4j_error: Optional[str] = None,
        postgres_error: Optional[str] = None
    ):
        self.neo4j_connected = neo4j_connected
        self.postgres_connected = postgres_connected
        self.neo4j_latency_ms = neo4j_latency_ms
        self.postgres_latency_ms = postgres_latency_ms
        self.timestamp = timestamp
        self.neo4j_error = neo4j_error
        self.postgres_error = postgres_error
    
    @property
    def is_healthy(self) -> bool:
        """Check if both connections are healthy."""
        return self.neo4j_connected and self.postgres_connected


class MockSearchResult:
    """Mock search result."""
    
    def __init__(
        self,
        id: str,
        type: str,
        source: str,
        score: float,
        data: Dict[str, Any]
    ):
        self.id = id
        self.type = type
        self.source = source
        self.score = score
        self.data = data


class MockGraphPostgresManager:
    """Mock implementation of GraphPostgresManager for testing.
    
    This class provides the same API as GraphPostgresManager but uses
    in-memory storage instead of real database connections.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize mock manager.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._data_store = InMemoryDataStore()
        
        # Create mock connections
        self.neo4j = MockNeo4jConnection(self._data_store, self.config)
        self.postgres = MockPostgresConnection(self._data_store, self.config)
        
        # Aliases for compatibility
        self._neo4j_conn = self.neo4j
        self._postgres_conn = self.postgres
        
        # State management
        self._is_initialized = False
        self._health_check_task: Optional[asyncio.Task] = None
        
        # Managers
        self._transaction_manager: Optional[MockTransactionManager] = None
        
        # Configuration
        self._error_rate = self.config.get("error_rate", 0.0)
        self._max_connections = self.config.get("max_connections", 100)
        self._timeout_simulation = self.config.get("timeout_simulation", False)
        
        # Call tracking
        self._call_history: List[Dict[str, Any]] = []
    
    @property
    def neo4j_connection(self):
        """Get Neo4j connection."""
        return self.neo4j
    
    @property
    def postgres_connection(self):
        """Get PostgreSQL connection."""
        return self.postgres
    
    async def initialize(self) -> None:
        """Initialize all connections."""
        if self._is_initialized:
            return
        
        # Simulate initialization delay
        await asyncio.sleep(0.01)
        
        # Connect to mock databases
        await asyncio.gather(
            self.neo4j.connect_with_retry(),
            self.postgres.connect_with_retry()
        )
        
        # Initialize transaction manager
        self._transaction_manager = MockTransactionManager(
            data_store=self._data_store,
            neo4j_connection=self.neo4j,
            postgres_connection=self.postgres,
            enable_two_phase_commit=self.config.get("enable_two_phase_commit", False),
            enable_logging=self.config.get("enable_transaction_logging", False)
        )
        
        # Start health check if configured
        health_check_interval = self.config.get("health_check_interval", 0)
        if health_check_interval > 0:
            self._health_check_task = asyncio.create_task(
                self._health_check_loop(health_check_interval)
            )
        
        self._is_initialized = True
    
    async def close(self) -> None:
        """Close all connections and clean up resources."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        await asyncio.gather(
            self.neo4j.disconnect(),
            self.postgres.disconnect(),
            return_exceptions=True
        )
        
        self._is_initialized = False
    
    async def health_check(self) -> MockHealthStatus:
        """Perform health check on all connections."""
        neo4j_health, neo4j_latency = await self.neo4j.health_check()
        postgres_health, postgres_latency = await self.postgres.health_check()
        
        return MockHealthStatus(
            neo4j_connected=neo4j_health,
            postgres_connected=postgres_health,
            neo4j_latency_ms=neo4j_latency,
            postgres_latency_ms=postgres_latency,
            timestamp=datetime.now(),
            neo4j_error=None if neo4j_health else "Mock connection failed",
            postgres_error=None if postgres_health else "Mock connection failed"
        )
    
    async def _health_check_loop(self, interval: float) -> None:
        """Background health check loop."""
        while True:
            try:
                await asyncio.sleep(interval)
                await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
    
    async def execute_neo4j_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute Cypher query on Neo4j."""
        self._record_call("execute_neo4j_query", {
            "query": query,
            "parameters": parameters,
            "database": database
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return await self.neo4j.execute_query(query, parameters, database)
    
    async def execute_postgres_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        fetch_all: bool = True
    ) -> List[Dict[str, Any]]:
        """Execute SQL query on PostgreSQL."""
        self._record_call("execute_postgres_query", {
            "query": query,
            "parameters": parameters,
            "fetch_all": fetch_all
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return await self.postgres.execute_query(query, parameters, fetch_all)
    
    async def batch_insert_neo4j(
        self,
        query: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000,
        database: Optional[str] = None
    ) -> int:
        """Batch insert data into Neo4j."""
        self._record_call("batch_insert_neo4j", {
            "query": query,
            "data_count": len(data),
            "batch_size": batch_size,
            "database": database
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return await self.neo4j.batch_insert(query, data, batch_size, database)
    
    async def batch_insert_postgres(
        self,
        query: str,
        data: List[Dict[str, Any]]
    ) -> int:
        """Batch insert data into PostgreSQL."""
        self._record_call("batch_insert_postgres", {
            "query": query,
            "data_count": len(data)
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return await self.postgres.execute_many(query, data)
    
    @asynccontextmanager
    async def transaction(self, timeout: Optional[float] = None):
        """Create transaction context."""
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        async with self._transaction_manager.begin_transaction(timeout) as tx:
            yield tx
    
    async def store_ast_graph(
        self,
        graph_data: Dict[str, Any],
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store AST graph data in Neo4j.
        
        Args:
            graph_data: Graph data with 'nodes' and 'edges'
            source_id: Source identifier
            metadata: Optional metadata
            
        Returns:
            Import statistics
        """
        self._record_call("store_ast_graph", {
            "source_id": source_id,
            "node_count": len(graph_data.get("nodes", [])),
            "edge_count": len(graph_data.get("edges", []))
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        # Validate graph data
        if "nodes" not in graph_data or "edges" not in graph_data:
            raise ValueError("Graph data must contain 'nodes' and 'edges'")
        
        nodes = graph_data["nodes"]
        edges = graph_data["edges"]
        
        # Store nodes
        node_mapping = {}
        for node in nodes:
            node_id = node.get("id", str(uuid.uuid4()))
            labels = node.get("labels", ["ASTNode"])
            properties = node.get("properties", {})
            properties["source_id"] = source_id
            if metadata:
                properties.update(metadata)
            
            new_id = self._data_store.create_node(labels, properties)
            node_mapping[node_id] = new_id
        
        # Store edges
        edge_count = 0
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in node_mapping and target in node_mapping:
                self._data_store.create_relationship(
                    node_mapping[source],
                    node_mapping[target],
                    edge.get("type", "CONNECTED_TO"),
                    edge.get("properties", {})
                )
                edge_count += 1
        
        return {
            "nodes_created": len(node_mapping),
            "edges_created": edge_count,
            "source_id": source_id,
            "status": "success"
        }
    
    async def search_unified(
        self,
        query: Union[str, Dict[str, Any]],
        include_graph: bool = True,
        include_text: bool = True,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 100
    ) -> List[MockSearchResult]:
        """Perform unified search across graph and text data.
        
        Args:
            query: Search query
            include_graph: Include graph search
            include_text: Include text search
            filters: Optional filters
            max_results: Maximum results
            
        Returns:
            List of search results
        """
        self._record_call("search_unified", {
            "query": query,
            "include_graph": include_graph,
            "include_text": include_text,
            "filters": filters,
            "max_results": max_results
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        results = []
        
        # Simple text search if query is string
        if isinstance(query, str) and include_text:
            matching_nodes = self._data_store.search_text(query)
            for node_id in list(matching_nodes)[:max_results]:
                node = self._data_store.get_node(node_id)
                if node:
                    results.append(MockSearchResult(
                        id=node_id,
                        type="node",
                        source="text_search",
                        score=1.0,
                        data=node
                    ))
        
        # Apply filters if provided
        if filters and results:
            filtered = []
            for result in results:
                if self._apply_filters(result, filters):
                    filtered.append(result)
            results = filtered
        
        return results[:max_results]
    
    # Intent Management
    
    async def link_intent_to_ast(
        self,
        intent_id: str,
        ast_node_ids: List[str],
        source_id: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        intent_vector: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Link intent data to AST nodes.
        
        Args:
            intent_id: Intent identifier
            ast_node_ids: List of AST node IDs to link
            source_id: Source code identifier
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata
            intent_vector: Optional 768-dimensional vector
            
        Returns:
            Linking results
        """
        self._record_call("link_intent_to_ast", {
            "intent_id": intent_id,
            "ast_node_ids": ast_node_ids,
            "source_id": source_id,
            "confidence": confidence
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        
        if intent_vector and len(intent_vector) != 768:
            raise ValueError(f"Vector must have 768 dimensions, got {len(intent_vector)}")
        
        # Store mappings
        mapping_ids = []
        for ast_node_id in ast_node_ids:
            mapping = {
                "id": str(uuid.uuid4()),
                "intent_id": intent_id,
                "ast_node_id": ast_node_id,
                "source_id": source_id,
                "confidence": confidence,
                "metadata": metadata or {},
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            self._data_store.add_intent_mapping(mapping)
            mapping_ids.append(mapping["id"])
        
        # Store vector if provided
        if intent_vector:
            self._data_store.add_intent_vector({
                "intent_id": intent_id,
                "vector": intent_vector,
                "metadata": metadata or {},
                "created_at": datetime.now()
            })
        
        return {
            "intent_id": intent_id,
            "mapped_ast_nodes": len(ast_node_ids),
            "mapping_ids": mapping_ids,
            "vector_stored": bool(intent_vector)
        }
    
    async def get_ast_nodes_by_intent(
        self,
        intent_id: str,
        min_confidence: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Get AST nodes linked to an intent.
        
        Args:
            intent_id: Intent identifier
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of AST node information
        """
        self._record_call("get_ast_nodes_by_intent", {
            "intent_id": intent_id,
            "min_confidence": min_confidence
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return self._data_store.get_intent_mappings(
            intent_id=intent_id,
            min_confidence=min_confidence
        )
    
    async def get_intents_for_ast(
        self,
        ast_node_id: str,
        min_confidence: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Get intents linked to an AST node.
        
        Args:
            ast_node_id: AST node identifier
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of intent information
        """
        self._record_call("get_intents_for_ast", {
            "ast_node_id": ast_node_id,
            "min_confidence": min_confidence
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return self._data_store.get_intent_mappings(
            ast_node_id=ast_node_id,
            min_confidence=min_confidence
        )
    
    async def search_ast_by_intent_vector(
        self,
        intent_vector: List[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for AST nodes by intent vector similarity.
        
        Args:
            intent_vector: 768-dimensional search vector
            limit: Maximum number of results
            threshold: Similarity threshold
            
        Returns:
            List of matching AST nodes
        """
        self._record_call("search_ast_by_intent_vector", {
            "vector_length": len(intent_vector),
            "limit": limit,
            "threshold": threshold
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        if len(intent_vector) != 768:
            raise ValueError(f"Vector must have 768 dimensions, got {len(intent_vector)}")
        
        return self._data_store.search_by_vector(
            intent_vector,
            limit=limit,
            threshold=threshold
        )
    
    async def update_intent_confidence(
        self,
        intent_id: str,
        ast_node_id: str,
        new_confidence: float
    ) -> bool:
        """Update confidence score for an intent-AST mapping.
        
        Args:
            intent_id: Intent identifier
            ast_node_id: AST node identifier
            new_confidence: New confidence score
            
        Returns:
            True if updated successfully
        """
        self._record_call("update_intent_confidence", {
            "intent_id": intent_id,
            "ast_node_id": ast_node_id,
            "new_confidence": new_confidence
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        if not 0.0 <= new_confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        
        return self._data_store.update_intent_confidence(
            intent_id, ast_node_id, new_confidence
        )
    
    async def remove_intent_mapping(
        self,
        intent_id: str,
        ast_node_id: Optional[str] = None
    ) -> int:
        """Remove intent-AST mappings.
        
        Args:
            intent_id: Intent identifier
            ast_node_id: Optional specific AST node
            
        Returns:
            Number of mappings removed
        """
        self._record_call("remove_intent_mapping", {
            "intent_id": intent_id,
            "ast_node_id": ast_node_id
        })
        
        if not self._is_initialized:
            raise RuntimeError("Manager not initialized")
        
        return self._data_store.remove_intent_mapping(intent_id, ast_node_id)
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get configuration information."""
        return {
            "neo4j_latency": self.config.get("neo4j_latency", 1),
            "postgres_latency": self.config.get("postgres_latency", 1),
            "error_rate": self._error_rate,
            "max_connections": self._max_connections
        }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        return {
            "initialized": self._is_initialized,
            "neo4j": {
                "state": self.neo4j.state.value,
                "connected": self.neo4j.is_connected
            },
            "postgres": {
                "state": self.postgres.state.value,
                "connected": self.postgres.is_connected
            }
        }
    
    # Mock-specific methods for testing
    
    def configure(self, config: Dict[str, Any]) -> None:
        """Update mock configuration."""
        self.config.update(config)
        self._error_rate = self.config.get("error_rate", 0.0)
        self._max_connections = self.config.get("max_connections", 100)
        self._timeout_simulation = self.config.get("timeout_simulation", False)
    
    def clear_data(self) -> None:
        """Clear all mock data."""
        self._data_store.clear()
        self._call_history.clear()
    
    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get history of method calls."""
        return self._call_history.copy()
    
    def assert_query_called(self, query: str) -> bool:
        """Assert that a specific query was called."""
        for call in self._call_history:
            if call["method"] in ["execute_neo4j_query", "execute_postgres_query"]:
                if query in call["args"].get("query", ""):
                    return True
        return False
    
    def assert_transaction_committed(self) -> bool:
        """Assert that a transaction was committed."""
        # Check transaction log in data store
        for tx in self._data_store.transaction_log:
            if tx.get("status") == "committed":
                return True
        return False
    
    def get_mock_stats(self) -> Dict[str, Any]:
        """Get mock statistics."""
        return self._data_store.get_stats()
    
    def _record_call(self, method: str, args: Dict[str, Any]) -> None:
        """Record a method call for testing."""
        self._call_history.append({
            "method": method,
            "args": args,
            "timestamp": time.time()
        })
    
    def _apply_filters(self, result: MockSearchResult, filters: Dict[str, Any]) -> bool:
        """Apply filters to a search result."""
        # Simple filter implementation
        for key, value in filters.items():
            if key == "node_types":
                if result.type not in value:
                    return False
            elif key == "source_ids":
                if result.data.get("properties", {}).get("source_id") not in value:
                    return False
        return True