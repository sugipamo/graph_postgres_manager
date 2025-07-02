"""Simple integration test for AST storage."""

import pytest

from graph_postgres_manager import GraphPostgresManager


@pytest.mark.asyncio
async def test_simple_ast_store():
    """Simple test to debug AST storage."""
    simple_graph = {
        "nodes": [
            {"id": "n1", "node_type": "Module", "source_id": "test"}
        ],
        "edges": []
    }
    
    async with GraphPostgresManager() as manager:
        print("Manager initialized")
        
        # Clean up
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'test'}) DELETE n"
        )
        print("Cleanup done")
        
        # Store
        result = await manager.store_ast_graph(
            graph_data=simple_graph,
            source_id="test"
        )
        print(f"Store result: {result}")
        
        # Verify
        count_result = await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'test'}) RETURN COUNT(n) AS count"
        )
        print(f"Count: {count_result[0]['count']}")
        
        # Clean up
        await manager.neo4j.execute_query(
            "MATCH (n:ASTNode {source_id: 'test'}) DELETE n"
        )