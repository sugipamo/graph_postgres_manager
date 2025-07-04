"""Integration tests for transaction management."""

import asyncio
from datetime import datetime

import pytest
import pytest_asyncio


@pytest.mark.integration
class TestTransactionIntegration:
    """Integration tests for transaction management."""
    
    @pytest_asyncio.fixture
    async def transaction_manager(self, manager):
        """Create and initialize transaction manager."""
        # Clean up test data
        try:
            await manager.execute_neo4j_query(
                "MATCH (n:TransactionTest) DETACH DELETE n"
            )
            await manager.execute_postgres_query(
                "DROP TABLE IF EXISTS transaction_test"
            )
            await manager.execute_postgres_query(
                """
                CREATE TABLE transaction_test (
                    id SERIAL PRIMARY KEY,
                    node_id VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        except Exception:
            pass
        
        yield manager
        
        # Cleanup
        try:
            await manager.execute_neo4j_query(
                "MATCH (n:TransactionTest) DETACH DELETE n"
            )
            await manager.execute_postgres_query(
                "DROP TABLE IF EXISTS transaction_test"
            )
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_simple_transaction_commit(self, transaction_manager):
        """Test simple transaction with successful commit."""
        node_id = "test-node-1"
        
        async with transaction_manager.transaction() as tx:
            # Create node in Neo4j
            await tx.neo4j_execute(
                "CREATE (n:TransactionTest {id: $id, created: $created})",
                {"id": node_id, "created": datetime.now().isoformat()}
            )
            
            # Create record in PostgreSQL
            await tx.postgres_execute(
                "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                {"node_id": node_id}
            )
        
        # Verify both operations were committed
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest {id: $id}) RETURN n",
            {"id": node_id}
        )
        assert len(neo4j_result) == 1
        assert neo4j_result[0]["n"]["id"] == node_id
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT * FROM transaction_test WHERE node_id = %(node_id)s",
            {"node_id": node_id}
        )
        assert len(postgres_result) == 1
        assert postgres_result[0]["node_id"] == node_id
    
    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, transaction_manager):
        """Test transaction rollback when error occurs."""
        node_id = "test-node-2"
        
        with pytest.raises(Exception, match="Simulated error"):
            async with transaction_manager.transaction() as tx:
                # Create node in Neo4j
                await tx.neo4j_execute(
                    "CREATE (n:TransactionTest {id: $id})",
                    {"id": node_id}
                )
                
                # Create record in PostgreSQL
                await tx.postgres_execute(
                    "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                    {"node_id": node_id}
                )
                
                # Force an error
                await tx.neo4j_execute("INVALID CYPHER QUERY")
        
        # Verify both operations were rolled back
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest {id: $id}) RETURN n",
            {"id": node_id}
        )
        assert len(neo4j_result) == 0
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT * FROM transaction_test WHERE node_id = %(node_id)s",
            {"node_id": node_id}
        )
        assert len(postgres_result) == 0
    
    @pytest.mark.asyncio
    async def test_manual_rollback(self, transaction_manager):
        """Test manual transaction rollback."""
        node_id = "test-node-3"
        
        async with transaction_manager.transaction() as tx:
            # Create node in Neo4j
            await tx.neo4j_execute(
                "CREATE (n:TransactionTest {id: $id})",
                {"id": node_id}
            )
            
            # Create record in PostgreSQL
            await tx.postgres_execute(
                "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                {"node_id": node_id}
            )
            
            # Manually rollback
            await tx.rollback()
        
        # Verify both operations were rolled back
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest {id: $id}) RETURN n",
            {"id": node_id}
        )
        assert len(neo4j_result) == 0
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT * FROM transaction_test WHERE node_id = %(node_id)s",
            {"node_id": node_id}
        )
        assert len(postgres_result) == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_transactions(self, transaction_manager):
        """Test multiple concurrent transactions."""
        async def create_node_and_record(tx_id: int):
            node_id = f"test-node-concurrent-{tx_id}"
            
            async with transaction_manager.transaction() as tx:
                # Add small delay to increase chance of concurrency issues
                await asyncio.sleep(0.1)
                
                await tx.neo4j_execute(
                    "CREATE (n:TransactionTest {id: $id, tx_id: $tx_id})",
                    {"id": node_id, "tx_id": tx_id}
                )
                
                await tx.postgres_execute(
                    "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                    {"node_id": node_id}
                )
        
        # Run multiple transactions concurrently
        tasks = [create_node_and_record(i) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # Verify all transactions completed successfully
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest) WHERE n.id STARTS WITH 'test-node-concurrent-' RETURN n"
        )
        assert len(neo4j_result) == 5
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT * FROM transaction_test WHERE node_id LIKE %s",
            ["test-node-concurrent-%"]
        )
        assert len(postgres_result) == 5
    
    @pytest.mark.asyncio
    async def test_transaction_timeout(self, transaction_manager):
        """Test transaction timeout."""
        node_id = "test-node-timeout"
        
        async def long_running_transaction():
            async with transaction_manager.transaction(timeout=0.5) as tx:
                # Create node in Neo4j
                await tx.neo4j_execute(
                    "CREATE (n:TransactionTest {id: $id})",
                    {"id": node_id}
                )
                
                # Simulate long-running operation
                await asyncio.sleep(1)
                
                # This should not execute due to timeout
                await tx.postgres_execute(
                    "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                    {"node_id": node_id}
                )
        
        with pytest.raises(asyncio.TimeoutError):
            await long_running_transaction()
        
        # Verify transaction was rolled back
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest {id: $id}) RETURN n",
            {"id": node_id}
        )
        assert len(neo4j_result) == 0
    
    @pytest.mark.asyncio
    async def test_batch_operations_in_transaction(self, transaction_manager):
        """Test batch operations within a transaction."""
        base_node_id = "test-batch-node"
        batch_size = 10
        
        async with transaction_manager.transaction() as tx:
            # Create multiple nodes in Neo4j
            for i in range(batch_size):
                await tx.neo4j_execute(
                    "CREATE (n:TransactionTest {id: $id, index: $index})",
                    {"id": f"{base_node_id}-{i}", "index": i}
                )
            
            # Create corresponding records in PostgreSQL
            for i in range(batch_size):
                await tx.postgres_execute(
                    "INSERT INTO transaction_test (node_id) VALUES (%(node_id)s)",
                    {"node_id": f"{base_node_id}-{i}"}
                )
        
        # Verify all operations were committed
        neo4j_result = await transaction_manager.execute_neo4j_query(
            "MATCH (n:TransactionTest) WHERE n.id STARTS WITH $base_id RETURN n",
            {"base_id": base_node_id}
        )
        assert len(neo4j_result) == batch_size
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT * FROM transaction_test WHERE node_id LIKE %(pattern)s",
            {"pattern": f"{base_node_id}-%"}
        )
        assert len(postgres_result) == batch_size
    
    @pytest.mark.asyncio
    async def test_transaction_with_relationships(self, transaction_manager):
        """Test transaction with Neo4j relationships."""
        user_id = "test-user-1"
        post_id = "test-post-1"
        
        async with transaction_manager.transaction() as tx:
            # Create user and post nodes
            await tx.neo4j_execute(
                """
                CREATE (u:TransactionTest:User {id: $user_id})
                CREATE (p:TransactionTest:Post {id: $post_id})
                CREATE (u)-[:AUTHORED]->(p)
                """,
                {"user_id": user_id, "post_id": post_id}
            )
            
            # Create records in PostgreSQL
            await tx.postgres_execute(
                "INSERT INTO transaction_test (node_id) VALUES (%(user_id)s), (%(post_id)s)",
                {"user_id": user_id, "post_id": post_id}
            )
        
        # Verify nodes and relationship were created
        neo4j_result = await transaction_manager.execute_neo4j_query(
            """
            MATCH (u:User {id: $user_id})-[:AUTHORED]->(p:Post {id: $post_id})
            RETURN u, p
            """,
            {"user_id": user_id, "post_id": post_id}
        )
        assert len(neo4j_result) == 1
        
        postgres_result = await transaction_manager.execute_postgres_query(
            "SELECT COUNT(*) as count FROM transaction_test "
            "WHERE node_id IN (%(user_id)s, %(post_id)s)",
            {"user_id": user_id, "post_id": post_id}
        )
        assert postgres_result[0]["count"] == 2