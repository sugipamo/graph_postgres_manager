"""Mock connection implementations for Neo4j and PostgreSQL.

This module provides mock connection classes that simulate the behavior
of real database connections without external dependencies.
"""

import asyncio
import time
from enum import Enum
from typing import Any

from .data_store import InMemoryDataStore


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class MockNeo4jConnection:
    """Mock implementation of Neo4j connection."""
    
    def __init__(self, data_store: InMemoryDataStore, config: dict[str, Any]):
        """Initialize mock Neo4j connection.
        
        Args:
            data_store: Shared in-memory data store
            config: Connection configuration
        """
        self.data_store = data_store
        self.config = config
        self.state = ConnectionState.DISCONNECTED
        self.is_connected = False
        self._latency_ms = config.get("neo4j_latency", 1)
    
    async def connect_with_retry(self) -> None:
        """Simulate connection with retry logic."""
        self.state = ConnectionState.CONNECTING
        await asyncio.sleep(self._latency_ms / 1000)
        self.state = ConnectionState.CONNECTED
        self.is_connected = True
    
    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self.state = ConnectionState.DISCONNECTING
        await asyncio.sleep(self._latency_ms / 1000)
        self.state = ConnectionState.DISCONNECTED
        self.is_connected = False
    
    async def health_check(self) -> tuple[bool, float]:
        """Perform health check.
        
        Returns:
            Tuple of (is_healthy, latency_ms)
        """
        start_time = time.time()
        await asyncio.sleep(self._latency_ms / 1000)
        latency = (time.time() - start_time) * 1000
        return self.is_connected, latency
    
    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher-like query.
        
        Args:
            query: Query string
            parameters: Query parameters
            database: Target database (ignored in mock)
            
        Returns:
            Query results
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Neo4j")
        
        start_time = time.time()
        await asyncio.sleep(self._latency_ms / 1000)
        
        # Simple query parsing for basic operations
        query_upper = query.upper()
        results = []
        
        if "CREATE" in query_upper:
            # Handle node creation
            if "NODE" in query_upper or "(" in query:
                labels = ["Node"]  # Default label
                properties = parameters or {}
                node_id = self.data_store.create_node(labels, properties)
                results.append({"id": node_id})
        
        elif "MATCH" in query_upper:
            # Handle simple match queries
            if parameters and "label" in parameters:
                nodes = self.data_store.get_nodes_by_label(parameters["label"])
                results = nodes
            else:
                # Return all nodes (simplified)
                results = [
                    self.data_store.get_node(node_id)
                    for node_id in list(self.data_store.nodes.keys())[:10]
                ]
                results = [r for r in results if r is not None]
        
        # Record operation time
        duration = time.time() - start_time
        self.data_store.record_operation_time(duration)
        
        return results
    
    async def batch_insert(
        self,
        query: str,
        data: list[dict[str, Any]],
        batch_size: int = 1000,
        database: str | None = None
    ) -> int:
        """Perform batch insert operation.
        
        Args:
            query: Query template
            data: List of data dictionaries
            batch_size: Batch size for processing
            database: Target database (ignored in mock)
            
        Returns:
            Number of inserted records
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Neo4j")
        
        inserted_count = 0
        
        # Process in batches
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            await asyncio.sleep(self._latency_ms / 1000)
            
            # Create nodes from batch data
            for item in batch:
                labels = item.get("labels", ["Node"])
                properties = item.get("properties", item)
                self.data_store.create_node(labels, properties)
                inserted_count += 1
        
        return inserted_count


class MockPostgresConnection:
    """Mock implementation of PostgreSQL connection."""
    
    def __init__(self, data_store: InMemoryDataStore, config: dict[str, Any]):
        """Initialize mock PostgreSQL connection.
        
        Args:
            data_store: Shared in-memory data store
            config: Connection configuration
        """
        self.data_store = data_store
        self.config = config
        self.state = ConnectionState.DISCONNECTED
        self.is_connected = False
        self._latency_ms = config.get("postgres_latency", 1)
    
    async def connect_with_retry(self) -> None:
        """Simulate connection with retry logic."""
        self.state = ConnectionState.CONNECTING
        await asyncio.sleep(self._latency_ms / 1000)
        self.state = ConnectionState.CONNECTED
        self.is_connected = True
        
        # Initialize default tables
        self._initialize_default_tables()
    
    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self.state = ConnectionState.DISCONNECTING
        await asyncio.sleep(self._latency_ms / 1000)
        self.state = ConnectionState.DISCONNECTED
        self.is_connected = False
    
    async def health_check(self) -> tuple[bool, float]:
        """Perform health check.
        
        Returns:
            Tuple of (is_healthy, latency_ms)
        """
        start_time = time.time()
        await asyncio.sleep(self._latency_ms / 1000)
        latency = (time.time() - start_time) * 1000
        return self.is_connected, latency
    
    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        fetch_all: bool = True
    ) -> list[dict[str, Any]]:
        """Execute an SQL-like query.
        
        Args:
            query: Query string
            parameters: Query parameters
            fetch_all: Whether to fetch all results
            
        Returns:
            Query results
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to PostgreSQL")
        
        start_time = time.time()
        await asyncio.sleep(self._latency_ms / 1000)
        
        # Simple query parsing
        query_upper = query.upper()
        results = []
        
        if "INSERT" in query_upper:
            # Handle simple insert
            table_name = self._extract_table_name(query)
            if table_name and parameters:
                self.data_store.insert_record(table_name, parameters)
                results.append({"inserted": 1})
        
        elif "SELECT" in query_upper:
            # Handle simple select
            table_name = self._extract_table_name(query)
            if table_name:
                where_clause = self._extract_where_clause(parameters)
                records = self.data_store.get_records(table_name, where_clause)
                results = records if fetch_all else records[:1]
        
        elif "CREATE TABLE" in query_upper:
            # Handle table creation
            table_name = self._extract_table_name(query)
            if table_name:
                self.data_store.create_table(table_name, {"id": "integer"})
                results.append({"created": table_name})
        
        # Record operation time
        duration = time.time() - start_time
        self.data_store.record_operation_time(duration)
        
        return results
    
    async def execute_many(
        self,
        query: str,
        data: list[dict[str, Any]]
    ) -> int:
        """Execute multiple queries.
        
        Args:
            query: Query template
            data: List of parameter dictionaries
            
        Returns:
            Number of affected rows
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to PostgreSQL")
        
        affected_rows = 0
        
        for params in data:
            await self.execute_query(query, params)
            affected_rows += 1
        
        return affected_rows
    
    def _initialize_default_tables(self) -> None:
        """Initialize default tables for metadata."""
        # Create metadata tables
        self.data_store.create_table("schema_metadata", {
            "id": "integer",
            "table_name": "text",
            "column_name": "text",
            "data_type": "text"
        })
        
        self.data_store.create_table("index_metadata", {
            "id": "integer",
            "index_name": "text",
            "table_name": "text",
            "columns": "text[]"
        })
        
        self.data_store.create_table("stats_metadata", {
            "id": "integer",
            "metric_name": "text",
            "value": "numeric",
            "timestamp": "timestamp"
        })
    
    def _extract_table_name(self, query: str) -> str | None:
        """Extract table name from query (simplified)."""
        query_upper = query.upper()
        
        # Try different patterns
        patterns = ["FROM ", "INTO ", "TABLE "]
        for pattern in patterns:
            if pattern in query_upper:
                idx = query_upper.index(pattern) + len(pattern)
                rest = query_upper[idx:].split()[0]
                return rest.lower().strip("();")
        
        return None
    
    def _extract_where_clause(self, parameters: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract WHERE clause conditions from parameters."""
        if not parameters:
            return None
        
        # Simple mapping - in real implementation would parse SQL
        return parameters