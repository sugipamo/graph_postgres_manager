"""Example usage of MockGraphPostgresManager.

This example demonstrates how to use the mock implementation
for testing without requiring actual database connections.
"""

import asyncio

from graph_postgres_manager.mocks import MockGraphPostgresManager


async def example_basic_usage():
    """Basic usage example."""
    print("=== Basic Usage Example ===")
    
    # Create and initialize mock manager
    async with MockGraphPostgresManager() as manager:
        # Execute Neo4j query
        result = await manager.execute_neo4j_query(
            "CREATE (p:Person {name: $name, age: $age}) RETURN p",
            {"name": "Alice", "age": 30}
        )
        print(f"Created person node: {result[0]['id']}")
        
        # Execute PostgreSQL query
        await manager.execute_postgres_query(
            "CREATE TABLE employees (id INTEGER, name TEXT, department TEXT)"
        )
        
        await manager.execute_postgres_query(
            "INSERT INTO employees VALUES (1, 'Alice', 'Engineering')"
        )
        
        # Check statistics
        stats = manager.get_mock_stats()
        print(f"Total nodes created: {stats['nodes_count']}")
        print(f"Total queries executed: {stats['query_count']}")


async def example_ast_graph_storage():
    """Example of storing AST graph data."""
    print("\n=== AST Graph Storage Example ===")
    
    async with MockGraphPostgresManager() as manager:
        # Simulate AST graph from ast2graph
        ast_graph = {
            "nodes": [
                {
                    "id": "func_main",
                    "labels": ["Function", "EntryPoint"],
                    "properties": {
                        "name": "main",
                        "line_start": 1,
                        "line_end": 20,
                        "complexity": 5
                    }
                },
                {
                    "id": "var_config",
                    "labels": ["Variable"],
                    "properties": {
                        "name": "config",
                        "type": "dict",
                        "line": 3
                    }
                },
                {
                    "id": "call_setup",
                    "labels": ["FunctionCall"],
                    "properties": {
                        "name": "setup",
                        "line": 5
                    }
                }
            ],
            "edges": [
                {
                    "source": "func_main",
                    "target": "var_config",
                    "type": "DECLARES"
                },
                {
                    "source": "func_main",
                    "target": "call_setup",
                    "type": "CALLS"
                }
            ]
        }
        
        # Store the graph
        result = await manager.store_ast_graph(
            ast_graph,
            source_id="main.py",
            metadata={"project": "example", "version": "1.0"}
        )
        
        print("Stored graph from main.py:")
        print(f"  - Nodes created: {result['nodes_created']}")
        print(f"  - Edges created: {result['edges_created']}")
        print(f"  - Status: {result['status']}")


async def example_search_functionality():
    """Example of unified search functionality."""
    print("\n=== Search Functionality Example ===")
    
    async with MockGraphPostgresManager() as manager:
        # Prepare test data
        graphs = [
            {
                "nodes": [
                    {
                        "id": "1",
                        "labels": ["Function"],
                        "properties": {"name": "process_user_data"}
                    },
                    {
                        "id": "2",
                        "labels": ["Function"],
                        "properties": {"name": "validate_user_input"}
                    },
                ],
                "edges": []
            },
            {
                "nodes": [
                    {"id": "3", "labels": ["Class"], "properties": {"name": "UserManager"}},
                    {"id": "4", "labels": ["Method"], "properties": {"name": "create_user"}},
                ],
                "edges": [{"source": "3", "target": "4", "type": "HAS_METHOD"}]
            }
        ]
        
        # Store multiple graphs
        for i, graph in enumerate(graphs):
            await manager.store_ast_graph(graph, f"module_{i}.py")
        
        # Search for "user" related items
        results = await manager.search_unified(
            "user",
            include_graph=True,
            include_text=True,
            max_results=10
        )
        
        print(f"Search results for 'user': {len(results)} items found")
        for result in results:
            props = result.data.get("properties", {})
            print(f"  - {props.get('name')} ({result.type})")


async def example_transaction_management():
    """Example of transaction management."""
    print("\n=== Transaction Management Example ===")
    
    async with MockGraphPostgresManager() as manager:
        # Successful transaction
        try:
            async with manager.transaction():
                # Create related data in both databases
                await manager.execute_neo4j_query(
                    "CREATE (u:User {id: $id, name: $name})",
                    {"id": 1, "name": "Bob"}
                )
                
                await manager.execute_postgres_query(
                    "CREATE TABLE IF NOT EXISTS user_profiles (user_id INTEGER, bio TEXT)"
                )
                
                await manager.execute_postgres_query(
                    "INSERT INTO user_profiles VALUES (1, 'Software Developer')"
                )
                
                print("Transaction completed successfully")
                
        except Exception as e:
            print(f"Transaction failed: {e}")
        
        # Verify transaction was committed
        if manager.assert_transaction_committed():
            print("Transaction was committed")


async def example_test_helpers():
    """Example of using test helper methods."""
    print("\n=== Test Helper Methods Example ===")
    
    # Configure mock with custom settings
    config = {
        "neo4j_latency": 5,      # 5ms latency for Neo4j
        "postgres_latency": 3,    # 3ms latency for PostgreSQL
        "error_rate": 0.0,        # No errors
        "health_check_interval": 1.0
    }
    
    manager = MockGraphPostgresManager(config)
    await manager.initialize()
    
    # Perform some operations
    await manager.execute_neo4j_query("CREATE (n:TestNode)")
    await manager.execute_postgres_query("SELECT 1")
    await manager.store_ast_graph(
        {"nodes": [{"id": "1", "labels": ["Node"], "properties": {"test": True}}], "edges": []},
        "test.py"
    )
    
    # Check call history
    history = manager.get_call_history()
    print(f"Total calls made: {len(history)}")
    for call in history:
        print(f"  - {call['method']}")
    
    # Assert specific queries were called
    if manager.assert_query_called("CREATE (n:TestNode)"):
        print("Neo4j CREATE query was called")
    
    if manager.assert_query_called("SELECT 1"):
        print("PostgreSQL SELECT query was called")
    
    # Get configuration info
    config_info = manager.get_config_info()
    print(f"Current configuration: {config_info}")
    
    # Get connection status
    status = manager.get_connection_status()
    print(f"Connection status: Neo4j={status['neo4j']['connected']}, PostgreSQL={status['postgres']['connected']}")
    
    await manager.close()


async def example_performance_testing():
    """Example of performance testing with mocks."""
    print("\n=== Performance Testing Example ===")
    
    async with MockGraphPostgresManager() as manager:
        import time
        
        # Measure bulk insertion performance
        start_time = time.time()
        
        # Create 1000 nodes
        nodes_data = [
            {"labels": ["Node"], "properties": {"id": i, "value": f"node_{i}"}}
            for i in range(1000)
        ]
        
        inserted = await manager.batch_insert_neo4j(
            "UNWIND $batch AS item CREATE (n:Node) SET n = item.properties",
            nodes_data,
            batch_size=100
        )
        
        elapsed = time.time() - start_time
        
        print(f"Inserted {inserted} nodes in {elapsed:.3f} seconds")
        print(f"Rate: {inserted/elapsed:.0f} nodes/second")
        
        # Check final statistics
        stats = manager.get_mock_stats()
        print("Final statistics:")
        print(f"  - Total nodes: {stats['nodes_count']}")
        print(f"  - Total queries: {stats['query_count']}")
        print(f"  - Average operation time: {stats['avg_operation_time']:.6f}s")


async def main():
    """Run all examples."""
    await example_basic_usage()
    await example_ast_graph_storage()
    await example_search_functionality()
    await example_transaction_management()
    await example_test_helpers()
    await example_performance_testing()


if __name__ == "__main__":
    asyncio.run(main())