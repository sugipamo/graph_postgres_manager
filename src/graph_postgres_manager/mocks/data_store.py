"""In-memory data store for mock implementations.

This module provides a zero-dependency, in-memory data store that simulates
Neo4j and PostgreSQL databases for testing purposes.
"""

import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any


class InMemoryDataStore:
    """In-memory data store for Neo4j and PostgreSQL mock data."""
    
    def __init__(self):
        """Initialize empty data structures."""
        # Neo4j data structures
        self.nodes: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, Any]] = []
        self.labels: dict[str, set[str]] = defaultdict(set)
        self.node_relationships: dict[str, list[int]] = defaultdict(list)
        
        # PostgreSQL data structures
        self.tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.schemas: dict[str, dict[str, str]] = {}
        self.indexes: dict[str, dict[str, Any]] = {}
        self.sequences: dict[str, int] = defaultdict(int)
        
        # Search indices (simplified)
        self.text_search: dict[str, set[str]] = defaultdict(set)
        self.vector_data: dict[str, list[float]] = {}
        
        # Intent management
        self.intent_mappings: list[dict[str, Any]] = []
        self.intent_vectors: dict[str, dict[str, Any]] = {}
        
        # Transaction management
        self.transaction_log: list[dict[str, Any]] = []
        self.active_transactions: dict[str, dict[str, Any]] = {}
        self.transaction_data: dict[str, dict[str, Any]] = {}
        
        # Statistics
        self.query_count = 0
        self.operation_times: list[float] = []
        self.last_reset_time = time.time()
    
    def clear(self) -> None:
        """Clear all data (for test isolation)."""
        self.__init__()
    
    def get_stats(self) -> dict[str, Any]:
        """Get current statistics about the data store."""
        return {
            "nodes_count": len(self.nodes),
            "relationships_count": len(self.relationships),
            "tables_count": len(self.tables),
            "query_count": self.query_count,
            "avg_operation_time": (
                sum(self.operation_times) / len(self.operation_times) 
                if self.operation_times else 0
            ),
            "uptime_seconds": time.time() - self.last_reset_time
        }
    
    def record_operation_time(self, duration: float) -> None:
        """Record operation execution time for statistics."""
        self.operation_times.append(duration)
        self.query_count += 1
    
    # Neo4j-specific methods
    
    def create_node(self, labels: list[str], properties: dict[str, Any]) -> str:
        """Create a new node with given labels and properties."""
        node_id = str(uuid.uuid4())
        
        # Store node data
        self.nodes[node_id] = {
            "labels": labels.copy(),
            "properties": properties.copy(),
            "created_at": time.time()
        }
        
        # Update label index
        for label in labels:
            self.labels[label].add(node_id)
        
        # Update text search index
        self._update_text_search_index(node_id, properties)
        
        return node_id
    
    def create_relationship(
        self, 
        source_id: str, 
        target_id: str,
        rel_type: str, 
        properties: dict[str, Any] | None = None
    ) -> int:
        """Create a relationship between two nodes."""
        if source_id not in self.nodes:
            raise ValueError(f"Source node {source_id} does not exist")
        if target_id not in self.nodes:
            raise ValueError(f"Target node {target_id} does not exist")
        
        rel_id = len(self.relationships)
        
        relationship = {
            "id": rel_id,
            "source": source_id,
            "target": target_id,
            "type": rel_type,
            "properties": properties.copy() if properties else {},
            "created_at": time.time()
        }
        
        self.relationships.append(relationship)
        self.node_relationships[source_id].append(rel_id)
        self.node_relationships[target_id].append(rel_id)
        
        return rel_id
    
    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            return {
                "id": node_id,
                "labels": node["labels"].copy(),
                "properties": node["properties"].copy()
            }
        return None
    
    def get_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        """Get all nodes with a specific label."""
        nodes = []
        for node_id in self.labels.get(label, set()):
            node = self.get_node(node_id)
            if node:
                nodes.append(node)
        return nodes
    
    def get_relationships_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Get all relationships connected to a node."""
        relationships = []
        for rel_id in self.node_relationships.get(node_id, []):
            if rel_id < len(self.relationships):
                relationships.append(self.relationships[rel_id].copy())
        return relationships
    
    # PostgreSQL-specific methods
    
    def create_table(self, table_name: str, schema: dict[str, str]) -> None:
        """Create a new table with the given schema."""
        self.schemas[table_name] = schema.copy()
        if table_name not in self.tables:
            self.tables[table_name] = []
    
    def insert_record(self, table_name: str, record: dict[str, Any]) -> int:
        """Insert a record into a table."""
        if table_name not in self.schemas:
            raise ValueError(f"Table {table_name} does not exist")
        
        # Auto-generate ID if needed
        if "id" in self.schemas[table_name] and "id" not in record:
            self.sequences[table_name] += 1
            record = record.copy()
            record["id"] = self.sequences[table_name]
        
        self.tables[table_name].append(record.copy())
        return len(self.tables[table_name]) - 1
    
    def get_records(
        self, 
        table_name: str, 
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None
    ) -> list[dict[str, Any]]:
        """Get records from a table with optional filtering."""
        if table_name not in self.tables:
            return []
        
        records = self.tables[table_name]
        
        # Apply WHERE clause
        if where:
            filtered = []
            for record in records:
                if all(
                    key in record and record[key] == value
                    for key, value in where.items()
                ):
                    filtered.append(record)
            records = filtered
        
        # Apply OFFSET and LIMIT
        if offset is not None:
            records = records[offset:]
        if limit is not None:
            records = records[:limit]
        
        # Return copies to prevent mutation
        return [record.copy() for record in records]
    
    def update_records(
        self, 
        table_name: str, 
        updates: dict[str, Any],
        where: dict[str, Any]
    ) -> int:
        """Update records in a table."""
        if table_name not in self.tables:
            return 0
        
        updated_count = 0
        for record in self.tables[table_name]:
            if all(
                key in record and record[key] == value
                for key, value in where.items()
            ):
                record.update(updates)
                updated_count += 1
        
        return updated_count
    
    def delete_records(self, table_name: str, where: dict[str, Any]) -> int:
        """Delete records from a table."""
        if table_name not in self.tables:
            return 0
        
        original_count = len(self.tables[table_name])
        
        self.tables[table_name] = [
            record for record in self.tables[table_name]
            if not all(
                key in record and record[key] == value
                for key, value in where.items()
            )
        ]
        
        return original_count - len(self.tables[table_name])
    
    # Transaction methods
    
    def begin_transaction(self, tx_id: str) -> None:
        """Begin a new transaction."""
        self.active_transactions[tx_id] = {
            "start_time": time.time(),
            "operations": [],
            "status": "active"
        }
        self.transaction_data[tx_id] = {
            "nodes": {},
            "relationships": [],
            "tables": defaultdict(list)
        }
    
    def add_transaction_operation(
        self, 
        tx_id: str, 
        operation: dict[str, Any]
    ) -> None:
        """Add an operation to a transaction."""
        if tx_id not in self.active_transactions:
            raise ValueError(f"Transaction {tx_id} does not exist")
        
        self.active_transactions[tx_id]["operations"].append(operation)
    
    def commit_transaction(self, tx_id: str) -> None:
        """Commit a transaction."""
        if tx_id not in self.active_transactions:
            raise ValueError(f"Transaction {tx_id} does not exist")
        
        # In this simple mock, we don't need to do anything special
        # since operations are applied immediately
        self.active_transactions[tx_id]["status"] = "committed"
        self.active_transactions[tx_id]["end_time"] = time.time()
        
        # Log the transaction
        self.transaction_log.append(self.active_transactions[tx_id].copy())
        
        # Clean up
        del self.active_transactions[tx_id]
        if tx_id in self.transaction_data:
            del self.transaction_data[tx_id]
    
    def rollback_transaction(self, tx_id: str) -> None:
        """Rollback a transaction."""
        if tx_id not in self.active_transactions:
            raise ValueError(f"Transaction {tx_id} does not exist")
        
        # In a real implementation, we would undo the operations
        # For this mock, we'll just mark it as rolled back
        self.active_transactions[tx_id]["status"] = "rolled_back"
        self.active_transactions[tx_id]["end_time"] = time.time()
        
        # Log the transaction
        self.transaction_log.append(self.active_transactions[tx_id].copy())
        
        # Clean up
        del self.active_transactions[tx_id]
        if tx_id in self.transaction_data:
            del self.transaction_data[tx_id]
    
    # Helper methods
    
    def _update_text_search_index(
        self, 
        node_id: str, 
        properties: dict[str, Any]
    ) -> None:
        """Update text search index with node properties."""
        for _key, value in properties.items():
            if isinstance(value, str):
                # Simple tokenization
                words = value.lower().split()
                for word in words:
                    self.text_search[word].add(node_id)
    
    def search_text(self, query: str) -> set[str]:
        """Simple text search across indexed content."""
        query_words = query.lower().split()
        if not query_words:
            return set()
        
        # Find nodes containing all query words (with partial matching)
        result_sets = []
        
        for query_word in query_words:
            matching_nodes = set()
            # Check each indexed word for partial match
            for indexed_word, node_ids in self.text_search.items():
                if query_word in indexed_word:
                    matching_nodes.update(node_ids)
            result_sets.append(matching_nodes)
        
        # Find intersection of all result sets
        if result_sets:
            result = result_sets[0]
            for s in result_sets[1:]:
                result &= s
            return result
        
        return set()
    
    # Intent management methods
    
    def add_intent_mapping(self, mapping: dict[str, Any]) -> None:
        """Add an intent-AST mapping."""
        self.intent_mappings.append(mapping)
    
    def add_intent_vector(self, vector_data: dict[str, Any]) -> None:
        """Add an intent vector."""
        self.intent_vectors[vector_data["intent_id"]] = vector_data
    
    def get_intent_mappings(
        self,
        intent_id: str | None = None,
        ast_node_id: str | None = None,
        min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """Get intent mappings filtered by criteria."""
        results = []
        
        for mapping in self.intent_mappings:
            # Apply filters
            if intent_id and mapping["intent_id"] != intent_id:
                continue
            if ast_node_id and mapping["ast_node_id"] != ast_node_id:
                continue
            if mapping["confidence"] < min_confidence:
                continue
            
            # Format result
            if intent_id:
                # Return AST node info
                results.append({
                    "ast_node_id": mapping["ast_node_id"],
                    "source_id": mapping["source_id"],
                    "confidence": mapping["confidence"],
                    "metadata": mapping["metadata"],
                    "created_at": (
                        mapping["created_at"].isoformat()
                        if mapping.get("created_at") else None
                    ),
                    "updated_at": (
                        mapping["updated_at"].isoformat()
                        if mapping.get("updated_at") else None
                    )
                })
            else:
                # Return intent info
                results.append({
                    "intent_id": mapping["intent_id"],
                    "source_id": mapping["source_id"],
                    "confidence": mapping["confidence"],
                    "metadata": mapping["metadata"],
                    "created_at": (
                        mapping["created_at"].isoformat()
                        if mapping.get("created_at") else None
                    ),
                    "updated_at": (
                        mapping["updated_at"].isoformat()
                        if mapping.get("updated_at") else None
                    )
                })
        
        return results
    
    def search_by_vector(
        self,
        query_vector: list[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Search for similar vectors using cosine similarity."""
        results = []
        
        # Simple cosine similarity calculation
        def cosine_similarity(v1: list[float], v2: list[float]) -> float:
            dot_product = sum(a * b for a, b in zip(v1, v2, strict=False))
            norm1 = sum(a * a for a in v1) ** 0.5
            norm2 = sum(b * b for b in v2) ** 0.5
            return dot_product / (norm1 * norm2) if norm1 * norm2 > 0 else 0
        
        # Search through stored vectors
        for intent_id, vector_data in self.intent_vectors.items():
            similarity = cosine_similarity(query_vector, vector_data["vector"])
            
            if similarity >= threshold:
                # Find mappings for this intent
                for mapping in self.intent_mappings:
                    if mapping["intent_id"] == intent_id:
                        results.append({
                            "ast_node_id": mapping["ast_node_id"],
                            "source_id": mapping["source_id"],
                            "confidence": mapping["confidence"],
                            "metadata": mapping["metadata"],
                            "similarity": similarity
                        })
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def update_intent_confidence(
        self,
        intent_id: str,
        ast_node_id: str,
        new_confidence: float
    ) -> bool:
        """Update confidence score for a specific mapping."""
        for mapping in self.intent_mappings:
            if mapping["intent_id"] == intent_id and mapping["ast_node_id"] == ast_node_id:
                mapping["confidence"] = new_confidence
                mapping["updated_at"] = datetime.now()
                return True
        return False
    
    def remove_intent_mapping(
        self,
        intent_id: str,
        ast_node_id: str | None = None
    ) -> int:
        """Remove intent mappings."""
        removed = 0
        
        # Filter out matching mappings
        if ast_node_id:
            # Remove specific mapping
            original_count = len(self.intent_mappings)
            self.intent_mappings = [
                m for m in self.intent_mappings
                if not (m["intent_id"] == intent_id and m["ast_node_id"] == ast_node_id)
            ]
            removed = original_count - len(self.intent_mappings)
        else:
            # Remove all mappings for intent
            original_count = len(self.intent_mappings)
            self.intent_mappings = [
                m for m in self.intent_mappings
                if m["intent_id"] != intent_id
            ]
            removed = original_count - len(self.intent_mappings)
            
            # Also remove vector if exists
            if intent_id in self.intent_vectors:
                del self.intent_vectors[intent_id]
        
        return removed