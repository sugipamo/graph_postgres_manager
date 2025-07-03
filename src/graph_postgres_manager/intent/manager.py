"""Intent management functionality for graph_postgres_manager."""

import json
from typing import Any

from ..connections.postgres import PostgresConnection
from ..exceptions import (
    DataOperationError,
    ValidationError,
)


class IntentManager:
    """Manages intent-to-AST mappings and vector operations."""
    
    def __init__(self, postgres_connection: PostgresConnection):
        """Initialize IntentManager with a PostgreSQL connection.
        
        Args:
            postgres_connection: PostgreSQL connection instance
        """
        self.postgres = postgres_connection
    
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
        
        Args:
            intent_id: Intent identifier
            ast_node_ids: List of AST node IDs to link
            source_id: Source code identifier
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata
            intent_vector: Optional 768-dimensional vector representation
            
        Returns:
            Created mapping information
            
        Raises:
            ValidationError: If parameters are invalid
            DataOperationError: If the operation fails
        """
        # Validate parameters
        if not intent_id or not ast_node_ids or not source_id:
            raise ValidationError("intent_id, ast_node_ids, and source_id are required")
        
        if not 0.0 <= confidence <= 1.0:
            raise ValidationError("confidence must be between 0.0 and 1.0")
        
        if intent_vector and len(intent_vector) != 768:
            raise ValidationError(f"Vector must have 768 dimensions, got {len(intent_vector)}")
        
        metadata = metadata or {}
        
        try:
            # Start transaction
            await self.postgres.execute("BEGIN")
            
            # Insert mappings
            mapping_ids = []
            for ast_node_id in ast_node_ids:
                query = """
                    INSERT INTO intent_ast_map 
                    (intent_id, ast_node_id, source_id, confidence, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (intent_id, ast_node_id) 
                    DO UPDATE SET 
                        source_id = EXCLUDED.source_id,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """
                result = await self.postgres.execute(
                    query, 
                    (intent_id, ast_node_id, source_id, confidence, json.dumps(metadata))
                )
                if result and len(result) > 0:
                    mapping_ids.append(str(result[0]["id"]))
            
            # Store vector if provided
            if intent_vector:
                vector_query = """
                    INSERT INTO intent_vectors (intent_id, vector, metadata)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (intent_id) 
                    DO UPDATE SET 
                        vector = EXCLUDED.vector,
                        metadata = EXCLUDED.metadata
                """
                # Convert list to PostgreSQL array
                await self.postgres.execute(
                    vector_query,
                    (intent_id, intent_vector, json.dumps(metadata))
                )
            
            # Commit transaction
            await self.postgres.execute("COMMIT")
            
            return {
                "intent_id": intent_id,
                "mapped_ast_nodes": len(ast_node_ids),
                "mapping_ids": mapping_ids,
                "vector_stored": bool(intent_vector)
            }
            
        except Exception as e:
            await self.postgres.execute("ROLLBACK")
            raise DataOperationError(f"Failed to link intent to AST: {e!s}") from e
    
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
            List of AST node information
        """
        query = """
            SELECT 
                ast_node_id,
                source_id,
                confidence,
                metadata,
                created_at,
                updated_at
            FROM intent_ast_map
            WHERE intent_id = %s AND confidence >= %s
            ORDER BY confidence DESC, created_at DESC
        """
        
        results = await self.postgres.execute(query, (intent_id, min_confidence))
        
        return [
            {
                "ast_node_id": row["ast_node_id"],
                "source_id": row["source_id"],
                "confidence": row["confidence"],
                "metadata": row["metadata"] or {},
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None
            }
            for row in results or []
        ]
    
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
            List of intent information
        """
        query = """
            SELECT 
                intent_id,
                source_id,
                confidence,
                metadata,
                created_at,
                updated_at
            FROM intent_ast_map
            WHERE ast_node_id = %s AND confidence >= %s
            ORDER BY confidence DESC, created_at DESC
        """
        
        results = await self.postgres.execute(query, (ast_node_id, min_confidence))
        
        return [
            {
                "intent_id": row["intent_id"],
                "source_id": row["source_id"],
                "confidence": row["confidence"],
                "metadata": row["metadata"] or {},
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None
            }
            for row in results or []
        ]
    
    async def search_ast_by_intent_vector(
        self,
        intent_vector: list[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Search for AST nodes by intent vector similarity.
        
        Args:
            intent_vector: 768-dimensional search vector
            limit: Maximum number of results
            threshold: Similarity threshold (0.0-1.0)
            
        Returns:
            List of matching AST nodes with similarity scores
        """
        if len(intent_vector) != 768:
            raise ValidationError(f"Vector must have 768 dimensions, got {len(intent_vector)}")
        
        # Without pgvector, we need to fetch vectors and calculate similarity in Python
        # First get all intent vectors
        vector_query = """
            SELECT intent_id, vector FROM intent_vectors
        """
        vector_results = await self.postgres.execute(vector_query)
        
        # Calculate similarities
        similarities = []
        for row in vector_results:
            intent_id = row["intent_id"]
            stored_vector = row["vector"]
            
            # Calculate cosine similarity
            dot_product = sum(a * b for a, b in zip(intent_vector, stored_vector, strict=False))
            norm1 = sum(a * a for a in intent_vector) ** 0.5
            norm2 = sum(b * b for b in stored_vector) ** 0.5
            similarity = dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
            
            if similarity >= threshold:
                similarities.append((intent_id, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        similarities = similarities[:limit]
        
        # Get corresponding AST mappings
        results = []
        for intent_id, similarity in similarities:
            mapping_query = """
                SELECT ast_node_id, source_id, confidence, metadata
                FROM intent_ast_map
                WHERE intent_id = %s
            """
            mappings = await self.postgres.execute(mapping_query, (intent_id,))
            
            for mapping in mappings:
                results.append({
                    "ast_node_id": mapping["ast_node_id"],
                    "source_id": mapping["source_id"],
                    "confidence": mapping["confidence"],
                    "metadata": mapping["metadata"] or {},
                    "similarity": similarity
                })
        
        return results
    
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
        if not 0.0 <= new_confidence <= 1.0:
            raise ValidationError("confidence must be between 0.0 and 1.0")
        
        query = """
            UPDATE intent_ast_map
            SET confidence = %s, updated_at = CURRENT_TIMESTAMP
            WHERE intent_id = %s AND ast_node_id = %s
        """
        
        await self.postgres.execute(query, (new_confidence, intent_id, ast_node_id))
        # For UPDATE queries, psycopg returns empty list when successful
        return True  # If no exception was raised, the update was successful
    
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
        if ast_node_id:
            query = "DELETE FROM intent_ast_map WHERE intent_id = %s AND ast_node_id = %s"
            params = (intent_id, ast_node_id)
        else:
            query = "DELETE FROM intent_ast_map WHERE intent_id = %s"
            params = (intent_id,)
        
        # For DELETE queries, we need to get the affected row count differently
        query_with_returning = query + " RETURNING 1"
        result = await self.postgres.execute(query_with_returning, params)
        return len(result) if result else 0
    
    async def batch_link_intents(
        self,
        mappings: list[tuple[str, list[str], str, float, dict[str, Any] | None]]
    ) -> dict[str, Any]:
        """Batch link multiple intents to AST nodes.
        
        Args:
            mappings: List of (intent_id, ast_node_ids, source_id, confidence, metadata) tuples
            
        Returns:
            Summary of batch operation
        """
        total_mappings = 0
        failed_mappings = 0
        
        try:
            await self.postgres.execute("BEGIN")
            
            for intent_id, ast_node_ids, source_id, confidence, metadata in mappings:
                try:
                    for ast_node_id in ast_node_ids:
                        query = """
                            INSERT INTO intent_ast_map 
                            (intent_id, ast_node_id, source_id, confidence, metadata)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (intent_id, ast_node_id) 
                            DO UPDATE SET 
                                source_id = EXCLUDED.source_id,
                                confidence = EXCLUDED.confidence,
                                metadata = EXCLUDED.metadata,
                                updated_at = CURRENT_TIMESTAMP
                        """
                        await self.postgres.execute(
                            query,
                            (intent_id, ast_node_id, source_id, confidence, 
                             json.dumps(metadata or {}))
                        )
                        total_mappings += 1
                except Exception:
                    failed_mappings += 1
            
            await self.postgres.execute("COMMIT")
            
        except Exception as e:
            await self.postgres.execute("ROLLBACK")
            raise DataOperationError(f"Batch link failed: {e!s}") from e
        
        return {
            "total_mappings": total_mappings,
            "failed_mappings": failed_mappings,
            "success_rate": (
                (total_mappings - failed_mappings) / total_mappings 
                if total_mappings > 0 else 0
            )
        }