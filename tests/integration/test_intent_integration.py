"""Integration tests for intent management functionality."""

import asyncio
import os
from typing import Any

import pytest

from graph_postgres_manager import GraphPostgresManager
from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.exceptions import ValidationError


@pytest.mark.integration
@pytest.mark.asyncio
class TestIntentIntegration:
    """Integration tests for intent-AST mapping functionality."""
    
    @pytest.fixture
    async def manager(self):
        """Create and initialize a GraphPostgresManager instance."""
        config = ConnectionConfig(
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "testpassword"),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_database=os.getenv("POSTGRES_DB", "testdb"),
            postgres_user=os.getenv("POSTGRES_USER", "testuser"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "testpassword"),
            max_retries=3,
            retry_delay=1.0,
        )
        
        manager = GraphPostgresManager(config)
        await manager.initialize()
        
        yield manager
        
        # Cleanup
        await manager.close()
    
    async def test_intent_ast_mapping_lifecycle(self, manager: GraphPostgresManager):
        """Test the complete lifecycle of intent-AST mappings."""
        # First, store some AST data
        ast_data = {
            "nodes": [
                {"id": "n1", "node_type": "FunctionDef", "value": "test_func", "lineno": 10},
                {"id": "n2", "node_type": "Assign", "value": "x", "lineno": 11},
                {"id": "n3", "node_type": "Return", "value": "x", "lineno": 12},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "CHILD"},
                {"source": "n2", "target": "n3", "type": "NEXT"},
            ]
        }
        
        source_id = "test_source_001"
        
        # Store AST graph
        ast_result = await manager.store_ast_graph(ast_data, source_id)
        assert ast_result["created_nodes"] == 3
        assert ast_result["created_edges"] == 2
        
        # Create intent-AST mappings
        intent_id = "intent_test_func_001"
        ast_node_ids = ["n1", "n2", "n3"]
        
        # Create a simple vector (normally would come from an embedding model)
        intent_vector = [0.1 * i for i in range(768)]
        
        link_result = await manager.link_intent_to_ast(
            intent_id=intent_id,
            ast_node_ids=ast_node_ids,
            source_id=source_id,
            confidence=0.95,
            metadata={"description": "Test function intent"},
            intent_vector=intent_vector
        )
        
        assert link_result["intent_id"] == intent_id
        assert link_result["mappings_created"] == 3
        assert link_result["vector_stored"] is True
        
        # Retrieve AST nodes by intent
        nodes = await manager.get_ast_nodes_by_intent(intent_id)
        assert len(nodes) == 3
        assert all(node["source_id"] == source_id for node in nodes)
        assert all(node["confidence"] == 0.95 for node in nodes)
        
        # Test vector search
        # Create a slightly different vector
        search_vector = [0.1 * i + 0.01 for i in range(768)]
        
        search_results = await manager.search_ast_by_intent_vector(
            intent_vector=search_vector,
            limit=5,
            threshold=0.5
        )
        
        # Should find our intent (if pgvector is available)
        if search_results:
            assert len(search_results) > 0
            assert search_results[0]["intent_id"] == intent_id
            assert len(search_results[0]["ast_nodes"]) == 3
        
        # Remove specific mapping
        removed_count = await manager.remove_intent_mapping(intent_id, "n2")
        assert removed_count == 1
        
        # Verify mapping was removed
        nodes = await manager.get_ast_nodes_by_intent(intent_id)
        assert len(nodes) == 2
        assert all(node["ast_node_id"] != "n2" for node in nodes)
        
        # Remove all remaining mappings
        removed_count = await manager.remove_intent_mapping(intent_id)
        assert removed_count == 2
        
        # Verify all mappings removed
        nodes = await manager.get_ast_nodes_by_intent(intent_id)
        assert len(nodes) == 0
    
    async def test_intent_validation(self, manager: GraphPostgresManager):
        """Test validation in intent operations."""
        # Test invalid confidence
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="test",
                ast_node_ids=["n1"],
                source_id="source1",
                confidence=2.0  # Invalid
            )
        
        # Test invalid vector dimensions
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="test",
                ast_node_ids=["n1"],
                source_id="source1",
                intent_vector=[1.0, 2.0, 3.0]  # Wrong size
            )
        
        # Test empty intent_id
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="",
                ast_node_ids=["n1"],
                source_id="source1"
            )
    
    async def test_concurrent_intent_operations(self, manager: GraphPostgresManager):
        """Test concurrent intent operations."""
        # Store AST data first
        ast_data = {
            "nodes": [
                {"id": f"node_{i}", "node_type": "Statement", "value": f"stmt_{i}"}
                for i in range(10)
            ],
            "edges": []
        }
        
        await manager.store_ast_graph(ast_data, "concurrent_source")
        
        # Create multiple intents concurrently
        tasks = []
        for i in range(5):
            intent_id = f"concurrent_intent_{i}"
            node_ids = [f"node_{j}" for j in range(i, min(i + 3, 10))]
            
            task = manager.link_intent_to_ast(
                intent_id=intent_id,
                ast_node_ids=node_ids,
                source_id="concurrent_source",
                confidence=0.8 + i * 0.02,
                metadata={"index": i}
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Verify all operations succeeded
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result["intent_id"] == f"concurrent_intent_{i}"
            assert result["mappings_created"] > 0
    
    async def test_intent_metadata_handling(self, manager: GraphPostgresManager):
        """Test metadata handling in intent operations."""
        # Store AST node
        ast_data = {
            "nodes": [{"id": "meta_node", "node_type": "Class", "value": "TestClass"}],
            "edges": []
        }
        await manager.store_ast_graph(ast_data, "meta_source")
        
        # Create intent with complex metadata
        metadata = {
            "description": "Test class for metadata",
            "tags": ["test", "class", "metadata"],
            "properties": {
                "visibility": "public",
                "abstract": False,
                "line_count": 50
            },
            "created_by": "test_user"
        }
        
        await manager.link_intent_to_ast(
            intent_id="meta_intent",
            ast_node_ids=["meta_node"],
            source_id="meta_source",
            metadata=metadata
        )
        
        # Retrieve and verify metadata
        nodes = await manager.get_ast_nodes_by_intent("meta_intent")
        assert len(nodes) == 1
        assert nodes[0]["metadata"] == metadata