"""Unit tests for MockGraphPostgresManager."""

import asyncio
import pytest

from graph_postgres_manager.mocks import MockGraphPostgresManager


class TestMockGraphPostgresManager:
    """Test MockGraphPostgresManager implementation."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test manager initialization."""
        manager = MockGraphPostgresManager()
        assert not manager._is_initialized
        
        await manager.initialize()
        assert manager._is_initialized
        assert manager.neo4j.is_connected
        assert manager.postgres.is_connected
        
        await manager.close()
        assert not manager._is_initialized
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with MockGraphPostgresManager() as manager:
            assert manager._is_initialized
            assert manager.neo4j.is_connected
            assert manager.postgres.is_connected
        
        # After exiting context, should be closed
        assert not manager._is_initialized
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check functionality."""
        async with MockGraphPostgresManager() as manager:
            status = await manager.health_check()
            
            assert status.neo4j_connected
            assert status.postgres_connected
            assert status.is_healthy
            assert status.neo4j_latency_ms > 0
            assert status.postgres_latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_neo4j_query_execution(self):
        """Test Neo4j query execution."""
        async with MockGraphPostgresManager() as manager:
            # Create a node
            result = await manager.execute_neo4j_query(
                "CREATE (n:TestNode {name: $name}) RETURN n",
                {"name": "test"}
            )
            
            assert len(result) == 1
            assert "id" in result[0]
            
            # Verify call was recorded
            assert manager.assert_query_called("CREATE")
    
    @pytest.mark.asyncio
    async def test_postgres_query_execution(self):
        """Test PostgreSQL query execution."""
        async with MockGraphPostgresManager() as manager:
            # Create table (mock handles this)
            await manager.execute_postgres_query(
                "CREATE TABLE test_table (id INTEGER, name TEXT)"
            )
            
            # Insert data
            await manager.execute_postgres_query(
                "INSERT INTO test_table VALUES ($1, $2)",
                {"id": 1, "name": "test"}
            )
            
            # Verify calls
            history = manager.get_call_history()
            assert len(history) == 2
            assert history[0]["method"] == "execute_postgres_query"
    
    @pytest.mark.asyncio
    async def test_batch_operations(self):
        """Test batch insert operations."""
        async with MockGraphPostgresManager() as manager:
            # Batch insert to Neo4j
            data = [
                {"labels": ["Node"], "properties": {"id": i, "name": f"node_{i}"}}
                for i in range(10)
            ]
            
            count = await manager.batch_insert_neo4j(
                "UNWIND $batch AS row CREATE (n:Node) SET n = row",
                data,
                batch_size=5
            )
            
            assert count == 10
            
            # Check stats
            stats = manager.get_mock_stats()
            assert stats["nodes_count"] == 10
    
    @pytest.mark.asyncio
    async def test_transaction_management(self):
        """Test transaction management."""
        async with MockGraphPostgresManager() as manager:
            # Use transaction
            async with manager.transaction() as tx:
                # Transaction should be active
                assert tx.tx_id in manager._data_store.active_transactions
                
                # Perform operations
                await manager.execute_neo4j_query(
                    "CREATE (n:TransactionNode)"
                )
                
                # Commit happens automatically
            
            # Verify transaction was committed
            assert manager.assert_transaction_committed()
    
    @pytest.mark.asyncio
    async def test_store_ast_graph(self):
        """Test AST graph storage."""
        async with MockGraphPostgresManager() as manager:
            graph_data = {
                "nodes": [
                    {"id": "n1", "labels": ["Function"], "properties": {"name": "test_func"}},
                    {"id": "n2", "labels": ["Variable"], "properties": {"name": "x"}}
                ],
                "edges": [
                    {"source": "n1", "target": "n2", "type": "CONTAINS"}
                ]
            }
            
            result = await manager.store_ast_graph(
                graph_data,
                source_id="test_file.py",
                metadata={"version": "1.0"}
            )
            
            assert result["nodes_created"] == 2
            assert result["edges_created"] == 1
            assert result["source_id"] == "test_file.py"
            assert result["status"] == "success"
            
            # Verify data in store
            stats = manager.get_mock_stats()
            assert stats["nodes_count"] == 2
            assert stats["relationships_count"] == 1
    
    @pytest.mark.asyncio
    async def test_unified_search(self):
        """Test unified search functionality."""
        async with MockGraphPostgresManager() as manager:
            # Add some test data
            graph_data = {
                "nodes": [
                    {"id": "n1", "labels": ["Function"], "properties": {"name": "calculate_sum"}},
                    {"id": "n2", "labels": ["Function"], "properties": {"name": "calculate_product"}}
                ],
                "edges": []
            }
            
            await manager.store_ast_graph(graph_data, "math_utils.py")
            
            # Search for "calculate"
            results = await manager.search_unified(
                "calculate",
                include_graph=True,
                include_text=True,
                max_results=10
            )
            
            assert len(results) == 2
            assert all(r.source == "text_search" for r in results)
            assert all("calculate" in r.data["properties"]["name"] for r in results)
    
    @pytest.mark.asyncio
    async def test_configuration(self):
        """Test configuration and mock behavior."""
        config = {
            "neo4j_latency": 10,
            "postgres_latency": 5,
            "error_rate": 0.0,
            "health_check_interval": 0.1
        }
        
        manager = MockGraphPostgresManager(config)
        await manager.initialize()
        
        # Check configuration
        config_info = manager.get_config_info()
        assert config_info["neo4j_latency"] == 10
        assert config_info["postgres_latency"] == 5
        
        # Health check should reflect latencies
        status = await manager.health_check()
        assert status.neo4j_latency_ms >= 10
        assert status.postgres_latency_ms >= 5
        
        await manager.close()
    
    @pytest.mark.asyncio
    async def test_clear_data(self):
        """Test data clearing functionality."""
        async with MockGraphPostgresManager() as manager:
            # Add some data
            await manager.execute_neo4j_query("CREATE (n:TestNode)")
            
            stats_before = manager.get_mock_stats()
            assert stats_before["nodes_count"] > 0
            
            # Clear data
            manager.clear_data()
            
            stats_after = manager.get_mock_stats()
            assert stats_after["nodes_count"] == 0
            assert len(manager.get_call_history()) == 0
    
    @pytest.mark.asyncio
    async def test_connection_status(self):
        """Test connection status reporting."""
        manager = MockGraphPostgresManager()
        
        # Before initialization
        status = manager.get_connection_status()
        assert not status["initialized"]
        assert status["neo4j"]["state"] == "disconnected"
        assert status["postgres"]["state"] == "disconnected"
        
        # After initialization
        await manager.initialize()
        status = manager.get_connection_status()
        assert status["initialized"]
        assert status["neo4j"]["state"] == "connected"
        assert status["postgres"]["state"] == "connected"
        
        await manager.close()


class TestMockSpecificFeatures:
    """Test mock-specific features for testing support."""
    
    @pytest.mark.asyncio
    async def test_call_history_tracking(self):
        """Test that all calls are tracked."""
        async with MockGraphPostgresManager() as manager:
            # Make various calls
            await manager.execute_neo4j_query("MATCH (n) RETURN n")
            await manager.execute_postgres_query("SELECT * FROM users")
            await manager.store_ast_graph(
                {"nodes": [], "edges": []},
                "empty.py"
            )
            
            history = manager.get_call_history()
            assert len(history) == 3
            
            # Check call details
            assert history[0]["method"] == "execute_neo4j_query"
            assert "MATCH" in history[0]["args"]["query"]
            
            assert history[1]["method"] == "execute_postgres_query"
            assert "SELECT" in history[1]["args"]["query"]
            
            assert history[2]["method"] == "store_ast_graph"
            assert history[2]["args"]["source_id"] == "empty.py"
    
    @pytest.mark.asyncio
    async def test_assertion_helpers(self):
        """Test assertion helper methods."""
        async with MockGraphPostgresManager() as manager:
            # Test query assertion
            await manager.execute_neo4j_query("CREATE (n:TestNode)")
            assert manager.assert_query_called("CREATE (n:TestNode)")
            assert not manager.assert_query_called("DELETE")
            
            # Test transaction assertion
            async with manager.transaction():
                await manager.execute_neo4j_query("CREATE (n:InTransaction)")
            
            assert manager.assert_transaction_committed()
    
    @pytest.mark.asyncio
    async def test_error_simulation(self):
        """Test error simulation capabilities."""
        # This is a placeholder for error simulation
        # In a full implementation, we would add error injection
        config = {"error_rate": 0.5}
        manager = MockGraphPostgresManager(config)
        
        # For now, just verify config is stored
        assert manager._error_rate == 0.5