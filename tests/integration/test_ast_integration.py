"""Integration tests for AST storage functionality."""

import pytest

from graph_postgres_manager import GraphPostgresManager


class TestASTIntegration:
    """Integration tests for AST storage in real databases."""

    @pytest.fixture
    def sample_ast_graph(self):
        """Sample AST graph data for testing."""
        return {
            "nodes": [
                {
                    "id": "module_test",
                    "node_type": "Module",
                    "source_id": "integration_test"
                },
                {
                    "id": "func_test",
                    "node_type": "FunctionDef",
                    "value": "test_function",
                    "lineno": 10,
                    "source_id": "integration_test"
                },
                {
                    "id": "arg_test",
                    "node_type": "arg",
                    "value": "x",
                    "lineno": 10,
                    "source_id": "integration_test"
                },
                {
                    "id": "return_test",
                    "node_type": "Return",
                    "lineno": 11,
                    "source_id": "integration_test"
                }
            ],
            "edges": [
                {
                    "source": "module_test",
                    "target": "func_test",
                    "type": "CHILD"
                },
                {
                    "source": "func_test",
                    "target": "arg_test",
                    "type": "CHILD"
                },
                {
                    "source": "func_test",
                    "target": "return_test",
                    "type": "CHILD"
                },
                {
                    "source": "arg_test",
                    "target": "return_test",
                    "type": "NEXT"
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_store_and_retrieve_ast_graph(self, sample_ast_graph, manager):
        """Test storing and retrieving AST graph in Neo4j."""
        # Clean up any existing test data
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test'}) DETACH DELETE n"
        )
        
        # Store the AST graph
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="integration_test"
        )
        
        assert result["created_nodes"] == 4
        assert result["created_edges"] == 4
        assert result["import_time_ms"] > 0
        assert result["nodes_per_second"] > 0
        
        # Verify nodes were created
        node_result = await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test'}) RETURN COUNT(n) AS count"
        )
        assert node_result[0]["count"] == 4
        
        # Verify specific node properties
        func_result = await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {id: 'func_test', source_id: 'integration_test'}) RETURN n"
        )
        func_node = func_result[0]["n"]
        assert func_node["node_type"] == "FunctionDef"
        assert func_node["value"] == "test_function"
        assert func_node["lineno"] == 10
        
        # Verify relationships
        rel_result = await manager.neo4j.execute_query(
            """
            MATCH (n:ASTNode {source_id: 'integration_test'})-[r]->
                  (m:ASTNode {source_id: 'integration_test'})
            RETURN TYPE(r) AS type, COUNT(r) AS count
            ORDER BY type
            """
        )
        relationships = {r["type"]: r["count"] for r in rel_result}
        assert relationships["CHILD"] == 3
        assert relationships["NEXT"] == 1
        
        # Cleanup
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test'}) DETACH DELETE n"
        )

    @pytest.mark.asyncio
    async def test_store_ast_graph_with_metadata(self, sample_ast_graph, manager):
        """Test storing AST graph with metadata."""
        # Clean up any existing test data
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test_meta'}) DETACH DELETE n"
        )
        
        metadata = {
            "file_path": "/test/file.py",
            "language": "python",
            "version": "3.12"
        }
        
        # Store the AST graph with metadata
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="integration_test_meta",
            metadata=metadata
        )
        
        assert result["created_nodes"] == 4
        
        # Verify metadata was stored
        node_result = await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test_meta'}) RETURN n LIMIT 1"
        )
        node = node_result[0]["n"]
        assert node["file_path"] == "/test/file.py"
        assert node["language"] == "python"
        assert node["version"] == "3.12"
        
        # Clean up
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'integration_test_meta'}) DETACH DELETE n"
        )

    @pytest.mark.asyncio
    async def test_store_large_ast_graph(self, manager):
        """Test storing a large AST graph to verify performance."""
        # Create a large tree structure
        large_graph = {
            "nodes": [],
            "edges": []
        }
        
        # Create a balanced tree with depth 5
        node_id = 0
        
        def create_subtree(parent_id, depth, max_depth=5, children_per_node=3):
            nonlocal node_id
            if depth >= max_depth:
                return
            
            for i in range(children_per_node):
                current_id = f"node_{node_id}"
                node_id += 1
                
                large_graph["nodes"].append({
                    "id": current_id,
                    "node_type": "Node",
                    "value": f"value_{node_id}",
                    "lineno": node_id,
                    "source_id": "performance_test"
                })
                
                if parent_id:
                    large_graph["edges"].append({
                        "source": parent_id,
                        "target": current_id,
                        "type": "CHILD"
                    })
                
                # Add NEXT relationship with previous sibling
                if i > 0:
                    prev_id = f"node_{node_id - 2}"
                    large_graph["edges"].append({
                        "source": prev_id,
                        "target": current_id,
                        "type": "NEXT"
                    })
                
                create_subtree(current_id, depth + 1)
        
        # Start creating the tree
        root_id = "root_node"
        large_graph["nodes"].append({
            "id": root_id,
            "node_type": "Module",
            "value": "root",
            "source_id": "performance_test"
        })
        create_subtree(root_id, 0)
        
        # Clean up any existing test data
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'performance_test'}) DETACH DELETE n"
        )
        
        # Store the large AST graph
        result = await manager.store_ast_graph(
            graph_data=large_graph,
            source_id="performance_test"
        )
        
        # Should have created many nodes (3^5 + 3^4 + ... + 3^1 + 1)
        expected_nodes = len(large_graph["nodes"])
        expected_edges = len(large_graph["edges"])
        
        assert result["created_nodes"] == expected_nodes
        assert result["created_edges"] == expected_edges
        assert result["import_time_ms"] > 0
        assert result["nodes_per_second"] > 0
        
        # Performance check - should handle 100+ nodes efficiently
        assert expected_nodes > 100
        assert result["nodes_per_second"] > 10  # At least 10 nodes per second
        
        # Clean up
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'performance_test'}) DETACH DELETE n"
        )

    @pytest.mark.asyncio
    async def test_store_ast_graph_idempotency(self, sample_ast_graph, manager):
        """Test that storing the same AST graph multiple times is idempotent."""
        # Clean up any existing test data
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'idempotency_test'}) DETACH DELETE n"
        )
        
        # Store the AST graph first time
        result1 = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="idempotency_test"
        )
        
        # Store the same AST graph second time
        result2 = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="idempotency_test"
        )
        
        # Both operations should succeed
        assert result1["created_nodes"] == 4
        assert result2["created_nodes"] == 4
        
        # Verify only one set of nodes exists
        node_result = await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'idempotency_test'}) RETURN COUNT(n) AS count"
        )
        assert node_result[0]["count"] == 4  # Should still be 4, not 8
        
        # Clean up
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'idempotency_test'}) DETACH DELETE n"
        )