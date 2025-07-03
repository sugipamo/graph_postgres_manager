"""Integration tests for intent functionality."""

import asyncio

import pytest

from graph_postgres_manager.exceptions import ValidationError


class TestIntentIntegration:
    """Integration tests for intent management."""
    
    @pytest.mark.asyncio
    async def test_intent_ast_lifecycle(self, manager, clean_databases):
        """Test complete lifecycle of intent-AST mappings."""
        # First, store some AST data
        ast_graph = {
            "nodes": [
                {
                    "id": "test_ast_1",
                    "node_type": "function",
                    "name": "test_function",
                    "source_id": "test_source"
                },
                {
                    "id": "test_ast_2",
                    "node_type": "class",
                    "name": "TestClass",
                    "source_id": "test_source"
                }
            ],
            "edges": [
                {
                    "source": "test_ast_2",
                    "target": "test_ast_1",
                    "type": "CHILD"
                }
            ],
            "source_id": "test_source",
            "metadata": {"language": "python"}
        }
        
        await manager.store_ast_graph(ast_graph, source_id=ast_graph["source_id"])
        
        # Link intent to AST nodes
        result = await manager.link_intent_to_ast(
            intent_id="test_intent_1",
            ast_node_ids=["test_ast_1", "test_ast_2"],
            source_id="test_source",
            confidence=0.95,
            metadata={"purpose": "testing"}
        )
        
        assert result["intent_id"] == "test_intent_1"
        assert result["mapped_ast_nodes"] == 2
        assert len(result["mapping_ids"]) == 2
        assert result["vector_stored"] is False
        
        # Get AST nodes by intent
        ast_nodes = await manager.get_ast_nodes_by_intent("test_intent_1")
        assert len(ast_nodes) == 2
        assert any(node["ast_node_id"] == "test_ast_1" for node in ast_nodes)
        assert any(node["ast_node_id"] == "test_ast_2" for node in ast_nodes)
        assert all(node["confidence"] == 0.95 for node in ast_nodes)
        
        # Get intents for AST node
        intents = await manager.get_intents_for_ast("test_ast_1")
        assert len(intents) == 1
        assert intents[0]["intent_id"] == "test_intent_1"
        assert intents[0]["confidence"] == 0.95
        
        # Update confidence
        updated = await manager.update_intent_confidence(
            intent_id="test_intent_1",
            ast_node_id="test_ast_1",
            new_confidence=0.8
        )
        assert updated is True
        
        # Verify update
        ast_nodes = await manager.get_ast_nodes_by_intent("test_intent_1")
        node1 = next(n for n in ast_nodes if n["ast_node_id"] == "test_ast_1")
        node2 = next(n for n in ast_nodes if n["ast_node_id"] == "test_ast_2")
        assert node1["confidence"] == 0.8
        assert node2["confidence"] == 0.95
        
        # Remove specific mapping
        removed = await manager.remove_intent_mapping(
            intent_id="test_intent_1",
            ast_node_id="test_ast_1"
        )
        assert removed == 1
        
        # Verify removal
        ast_nodes = await manager.get_ast_nodes_by_intent("test_intent_1")
        assert len(ast_nodes) == 1
        assert ast_nodes[0]["ast_node_id"] == "test_ast_2"
        
        # Remove all remaining mappings
        removed = await manager.remove_intent_mapping("test_intent_1")
        assert removed == 1
        
        # Verify complete removal
        ast_nodes = await manager.get_ast_nodes_by_intent("test_intent_1")
        assert len(ast_nodes) == 0
    
    @pytest.mark.asyncio
    async def test_intent_vector_search(self, manager, clean_databases):
        """Test vector-based intent search."""
        # Create test vector (normally from embedding model)
        test_vector = [0.1] * 768
        similar_vector = [0.1] * 768
        similar_vector[0] = 0.11  # Slightly different
        
        # Store AST and link with vector
        ast_graph = {
            "nodes": [
                {
                    "id": "vec_ast_1",
                    "node_type": "function",
                    "name": "vector_function",
                    "source_id": "vec_source"
                }
            ],
            "edges": [],
            "source_id": "vec_source"
        }
        
        await manager.store_ast_graph(ast_graph, source_id=ast_graph["source_id"])
        
        # Link with vector
        result = await manager.link_intent_to_ast(
            intent_id="vec_intent_1",
            ast_node_ids=["vec_ast_1"],
            source_id="vec_source",
            intent_vector=test_vector
        )
        
        assert result["vector_stored"] is True
        
        # Search with similar vector
        results = await manager.search_ast_by_intent_vector(
            intent_vector=similar_vector,
            limit=10,
            threshold=0.9
        )
        
        assert len(results) == 1
        assert results[0]["ast_node_id"] == "vec_ast_1"
        assert results[0]["similarity"] > 0.9
        
        # Search with very different vector (should not match)
        different_vector = [-0.1] * 768  # Negative correlation
        results = await manager.search_ast_by_intent_vector(
            intent_vector=different_vector,
            limit=10,
            threshold=0.5  # Lower threshold as negative correlation should be < 0
        )
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_intent_validation(self, manager):
        """Test validation of intent operations."""
        # Invalid confidence
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="test_intent",
                ast_node_ids=["test_ast"],
                source_id="test_source",
                confidence=2.0  # Invalid
            )
        
        # Invalid vector dimensions
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="test_intent",
                ast_node_ids=["test_ast"],
                source_id="test_source",
                intent_vector=[0.1] * 100  # Wrong size
            )
        
        # Empty required fields
        with pytest.raises(ValidationError):
            await manager.link_intent_to_ast(
                intent_id="",  # Empty
                ast_node_ids=["test_ast"],
                source_id="test_source"
            )
    
    @pytest.mark.asyncio
    async def test_intent_with_unified_search(self, manager, clean_databases):
        """Test intent integration with unified search."""
        # Store AST with intent
        ast_graph = {
            "nodes": [
                {
                    "id": "search_ast_1",
                    "node_type": "function",
                    "name": "search_function",
                    "source_id": "search_source",
                    "docstring": "Function for searching data"
                }
            ],
            "edges": [],
            "source_id": "search_source"
        }
        
        await manager.store_ast_graph(ast_graph, source_id=ast_graph["source_id"])
        
        # Link intent
        await manager.link_intent_to_ast(
            intent_id="search_intent_1",
            ast_node_ids=["search_ast_1"],
            source_id="search_source",
            metadata={"tags": ["search", "data"]}
        )
        
        # Perform unified search
        results = await manager.search_unified(
            query="search",
            include_graph=True,
            include_text=True
        )
        
        # Should find the node through graph search
        assert any(r.id == "search_ast_1" for r in results)
    
    @pytest.mark.asyncio
    async def test_concurrent_intent_operations(self, manager, clean_databases):
        """Test concurrent intent operations."""
        # Store base AST
        ast_graph = {
            "nodes": [
                {
                    "id": f"concurrent_ast_{i}",
                    "node_type": "function",
                    "name": f"func_{i}",
                    "source_id": "concurrent_source"
                }
                for i in range(5)
            ],
            "edges": [],
            "source_id": "concurrent_source"
        }
        
        await manager.store_ast_graph(ast_graph, source_id=ast_graph["source_id"])
        
        # Create multiple intent mappings concurrently
        tasks = []
        for i in range(5):
            task = manager.link_intent_to_ast(
                intent_id=f"concurrent_intent_{i}",
                ast_node_ids=[f"concurrent_ast_{i}"],
                source_id="concurrent_source",
                confidence=0.9 - (i * 0.1)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Verify all succeeded
        assert len(results) == 5
        assert all(r["mapped_ast_nodes"] == 1 for r in results)
        
        # Query all mappings
        all_mappings = []
        for i in range(5):
            nodes = await manager.get_ast_nodes_by_intent(f"concurrent_intent_{i}")
            all_mappings.extend(nodes)
        
        assert len(all_mappings) == 5
        assert len({m["ast_node_id"] for m in all_mappings}) == 5