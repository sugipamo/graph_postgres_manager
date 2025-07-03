"""Intent manager for handling intent-AST mappings."""

import json
import logging
from typing import Any

from ..connections import PostgresConnection
from ..exceptions import DataOperationError, ValidationError

logger = logging.getLogger(__name__)


class IntentManager:
    """Manages intent-AST mappings and vector search operations."""
    
    def __init__(self, postgres_connection: PostgresConnection):
        """Initialize the IntentManager.
        
        Args:
            postgres_connection: PostgreSQL connection instance
        """
        self.postgres = postgres_connection
        self._schema_initialized = False
    
    async def initialize_schema(self) -> None:
        """Initialize the intent-related database schema."""
        if self._schema_initialized:
            return
        
        logger.info("Initializing intent schema")
        
        create_intent_ast_map = """
        CREATE TABLE IF NOT EXISTS intent_ast_map (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            intent_id VARCHAR(255) NOT NULL,
            ast_node_id VARCHAR(255) NOT NULL,
            source_id VARCHAR(255) NOT NULL,
            confidence FLOAT DEFAULT 1.0,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(intent_id, ast_node_id)
        );
        """
        
        create_indexes = """
        CREATE INDEX IF NOT EXISTS idx_intent_ast_intent_id ON intent_ast_map(intent_id);
        CREATE INDEX IF NOT EXISTS idx_intent_ast_node_id ON intent_ast_map(ast_node_id);
        CREATE INDEX IF NOT EXISTS idx_intent_ast_source_id ON intent_ast_map(source_id);
        """
        
        # Check if pgvector extension is available
        check_pgvector = """
        SELECT EXISTS (
            SELECT 1 FROM pg_extension WHERE extname = 'vector'
        );
        """
        
        async with self.postgres.get_connection() as conn:
            # Create intent_ast_map table
            await conn.execute(create_intent_ast_map)
            await conn.execute(create_indexes)
            
            # Check for pgvector
            result = await conn.fetchone(check_pgvector)
            has_pgvector = result[0] if result else False
            
            if has_pgvector:
                # Create vector table if pgvector is available
                create_intent_vectors = """
                CREATE TABLE IF NOT EXISTS intent_vectors (
                    intent_id VARCHAR(255) PRIMARY KEY,
                    vector vector(768) NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
                
                create_vector_index = """
                CREATE INDEX IF NOT EXISTS idx_intent_vectors_vector 
                ON intent_vectors USING ivfflat (vector vector_cosine_ops)
                WITH (lists = 100);
                """
                
                await conn.execute(create_intent_vectors)
                await conn.execute(create_vector_index)
                logger.info("pgvector support enabled for intent vectors")
            else:
                logger.warning("pgvector extension not available - vector search disabled")
        
        self._schema_initialized = True
        logger.info("Intent schema initialized successfully")
    
    async def link_intent_to_ast(
        self,
        intent_id: str,
        ast_node_ids: list[str],
        source_id: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        intent_vector: list[float] | None = None
    ) -> dict[str, Any]:
        """Link an intent to one or more AST nodes.
        
        Args:
            intent_id: Intent identifier
            ast_node_ids: List of AST node identifiers to link
            source_id: Source code identifier
            confidence: Confidence level of the mapping (0.0-1.0)
            metadata: Additional metadata
            intent_vector: Optional 768-dimensional vector representation
            
        Returns:
            Dictionary with mapping results
            
        Raises:
            ValidationError: If input validation fails
            DataOperationError: If database operation fails
        """
        # Validate inputs
        if not intent_id:
            raise ValidationError("intent_id is required")
        if not ast_node_ids:
            raise ValidationError("ast_node_ids cannot be empty")
        if not source_id:
            raise ValidationError("source_id is required")
        if not 0.0 <= confidence <= 1.0:
            raise ValidationError("confidence must be between 0.0 and 1.0")
        
        if intent_vector:
            if len(intent_vector) != 768:
                raise ValidationError("intent_vector must have exactly 768 dimensions")
            if not all(isinstance(x, (int, float)) for x in intent_vector):
                raise ValidationError("intent_vector must contain only numeric values")
        
        try:
            async with self.postgres.get_connection() as conn:
                async with conn.transaction():
                    # Insert mappings
                    insert_mapping = """
                    INSERT INTO intent_ast_map 
                    (intent_id, ast_node_id, source_id, confidence, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (intent_id, ast_node_id) 
                    DO UPDATE SET 
                        source_id = EXCLUDED.source_id,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, created_at, updated_at;
                    """
                    
                    mappings_created = []
                    for ast_node_id in ast_node_ids:
                        result = await conn.fetchone(
                            insert_mapping,
                            intent_id,
                            ast_node_id,
                            source_id,
                            confidence,
                            json.dumps(metadata) if metadata else None
                        )
                        
                        if result:
                            mappings_created.append({
                                "id": str(result[0]),
                                "ast_node_id": ast_node_id,
                                "created_at": result[1].isoformat(),
                                "updated_at": result[2].isoformat()
                            })
                    
                    # Store vector if provided
                    vector_stored = False
                    if intent_vector:
                        # Check if vector table exists
                        check_vector_table = """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_name = 'intent_vectors'
                        );
                        """
                        
                        result = await conn.fetchone(check_vector_table)
                        if result and result[0]:
                            insert_vector = """
                            INSERT INTO intent_vectors (intent_id, vector, metadata)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (intent_id) 
                            DO UPDATE SET 
                                vector = EXCLUDED.vector,
                                metadata = EXCLUDED.metadata;
                            """
                            
                            vector_str = "[" + ",".join(str(v) for v in intent_vector) + "]"
                            await conn.execute(
                                insert_vector,
                                intent_id,
                                vector_str,
                                json.dumps(metadata) if metadata else None
                            )
                            vector_stored = True
                    
                    return {
                        "intent_id": intent_id,
                        "source_id": source_id,
                        "mappings_created": len(mappings_created),
                        "mappings": mappings_created,
                        "vector_stored": vector_stored
                    }
                    
        except Exception as e:
            error_msg = f"Failed to link intent to AST: {e}"
            logger.error(error_msg)
            raise DataOperationError(error_msg) from e
    
    async def get_ast_nodes_by_intent(
        self,
        intent_id: str,
        source_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all AST nodes linked to an intent.
        
        Args:
            intent_id: Intent identifier
            source_id: Optional source filter
            
        Returns:
            List of AST node mappings
        """
        query = """
        SELECT 
            id, ast_node_id, source_id, confidence, 
            metadata, created_at, updated_at
        FROM intent_ast_map
        WHERE intent_id = $1
        """
        
        params = [intent_id]
        if source_id:
            query += " AND source_id = $2"
            params.append(source_id)
        
        query += " ORDER BY confidence DESC, created_at DESC"
        
        try:
            async with self.postgres.get_connection() as conn:
                results = await conn.fetch(query, *params)
                
                return [
                    {
                        "id": str(row[0]),
                        "ast_node_id": row[1],
                        "source_id": row[2],
                        "confidence": row[3],
                        "metadata": json.loads(row[4]) if row[4] else None,
                        "created_at": row[5].isoformat(),
                        "updated_at": row[6].isoformat()
                    }
                    for row in results
                ]
                
        except Exception as e:
            error_msg = f"Failed to get AST nodes by intent: {e}"
            logger.error(error_msg)
            raise DataOperationError(error_msg) from e
    
    async def search_ast_by_intent_vector(
        self,
        intent_vector: list[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Search for AST nodes using intent vector similarity.
        
        Args:
            intent_vector: 768-dimensional search vector
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0.0-1.0)
            
        Returns:
            List of similar intents with their AST mappings
            
        Raises:
            ValidationError: If inputs are invalid
            DataOperationError: If search fails
        """
        if len(intent_vector) != 768:
            raise ValidationError("intent_vector must have exactly 768 dimensions")
        if not 0.0 <= threshold <= 1.0:
            raise ValidationError("threshold must be between 0.0 and 1.0")
        if limit <= 0:
            raise ValidationError("limit must be positive")
        
        try:
            async with self.postgres.get_connection() as conn:
                # Check if vector table exists
                check_table = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'intent_vectors'
                );
                """
                
                result = await conn.fetchone(check_table)
                if not result or not result[0]:
                    return []
                
                # Search for similar vectors
                vector_str = "[" + ",".join(str(v) for v in intent_vector) + "]"
                
                search_query = """
                SELECT 
                    iv.intent_id,
                    1 - (iv.vector <=> $1::vector) as similarity,
                    iv.metadata as intent_metadata,
                    iam.ast_node_id,
                    iam.source_id,
                    iam.confidence,
                    iam.metadata as mapping_metadata
                FROM intent_vectors iv
                JOIN intent_ast_map iam ON iv.intent_id = iam.intent_id
                WHERE 1 - (iv.vector <=> $1::vector) >= $2
                ORDER BY similarity DESC, iam.confidence DESC
                LIMIT $3;
                """
                
                results = await conn.fetch(search_query, vector_str, threshold, limit)
                
                # Group results by intent
                intent_results = {}
                for row in results:
                    intent_id = row[0]
                    if intent_id not in intent_results:
                        intent_results[intent_id] = {
                            "intent_id": intent_id,
                            "similarity": row[1],
                            "intent_metadata": json.loads(row[2]) if row[2] else None,
                            "ast_nodes": []
                        }
                    
                    intent_results[intent_id]["ast_nodes"].append({
                        "ast_node_id": row[3],
                        "source_id": row[4],
                        "confidence": row[5],
                        "metadata": json.loads(row[6]) if row[6] else None
                    })
                
                return list(intent_results.values())
                
        except Exception as e:
            error_msg = f"Failed to search AST by intent vector: {e}"
            logger.error(error_msg)
            raise DataOperationError(error_msg) from e
    
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
        query = "DELETE FROM intent_ast_map WHERE intent_id = $1"
        params = [intent_id]
        
        if ast_node_id:
            query += " AND ast_node_id = $2"
            params.append(ast_node_id)
        
        try:
            async with self.postgres.get_connection() as conn:
                result = await conn.execute(query, *params)
                # Extract row count from result string
                count = int(result.split()[-1]) if result else 0
                
                # Also remove vector if all mappings removed
                if not ast_node_id and count > 0:
                    await conn.execute(
                        "DELETE FROM intent_vectors WHERE intent_id = $1",
                        intent_id
                    )
                
                return count
                
        except Exception as e:
            error_msg = f"Failed to remove intent mapping: {e}"
            logger.error(error_msg)
            raise DataOperationError(error_msg) from e