"""
データ操作の統合テスト
"""
import json

import pytest

from graph_postgres_manager import GraphPostgresManager


class TestDataOperations:
    """データ操作のテストクラス"""
    
    @pytest.mark.asyncio
    async def test_neo4j_node_crud(self, manager: GraphPostgresManager, clean_neo4j):
        """Neo4jのノードCRUD操作テスト"""
        # Create
        create_query = """
        CREATE (n:Person {name: $name, age: $age, created_at: datetime()})
        RETURN n
        """
        result = await manager.neo4j_connection.execute_query(
            create_query, name="Alice", age=30
        )
        assert len(result) == 1
        assert result[0]["n"]["name"] == "Alice"
        assert result[0]["n"]["age"] == 30
        
        # Read
        read_query = "MATCH (n:Person {name: $name}) RETURN n"
        result = await manager.neo4j_connection.execute_query(read_query, name="Alice")
        assert len(result) == 1
        assert result[0]["n"]["name"] == "Alice"
        
        # Update
        update_query = """
        MATCH (n:Person {name: $name})
        SET n.age = $new_age, n.updated_at = datetime()
        RETURN n
        """
        result = await manager.neo4j_connection.execute_query(
            update_query, name="Alice", new_age=31
        )
        assert result[0]["n"]["age"] == 31
        
        # Delete
        delete_query = "MATCH (n:Person {name: $name}) DELETE n"
        await manager.neo4j_connection.execute_query(delete_query, name="Alice")
        
        # Verify deletion
        result = await manager.neo4j_connection.execute_query(read_query, name="Alice")
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_neo4j_relationship_crud(self, manager: GraphPostgresManager, clean_neo4j):
        """Neo4jのリレーションシップCRUD操作テスト"""
        # Create nodes and relationship
        create_query = """
        CREATE (a:Person {name: 'Alice'})
        CREATE (b:Person {name: 'Bob'})
        CREATE (a)-[r:KNOWS {since: 2020}]->(b)
        RETURN a, r, b
        """
        result = await manager.neo4j_connection.execute_query(create_query)
        assert len(result) == 1
        assert result[0]["r"]["since"] == 2020
        
        # Read relationship
        read_query = """
        MATCH (a:Person {name: 'Alice'})-[r:KNOWS]->(b:Person {name: 'Bob'})
        RETURN r
        """
        result = await manager.neo4j_connection.execute_query(read_query)
        assert len(result) == 1
        assert result[0]["r"]["since"] == 2020
        
        # Update relationship
        update_query = """
        MATCH (a:Person {name: 'Alice'})-[r:KNOWS]->(b:Person {name: 'Bob'})
        SET r.status = 'close_friends'
        RETURN r
        """
        result = await manager.neo4j_connection.execute_query(update_query)
        assert result[0]["r"]["status"] == "close_friends"
        
        # Delete relationship
        delete_query = """
        MATCH (a:Person {name: 'Alice'})-[r:KNOWS]->(b:Person {name: 'Bob'})
        DELETE r
        """
        await manager.neo4j_connection.execute_query(delete_query)
        
        # Verify deletion
        result = await manager.neo4j_connection.execute_query(read_query)
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_postgres_crud(self, manager: GraphPostgresManager, clean_postgres):
        """PostgreSQLのCRUD操作テスト"""
        # Create
        insert_query = """
        INSERT INTO graph_data.metadata (key, value)
        VALUES ($1, $2)
        RETURNING id, key, value, created_at
        """
        test_data = {"type": "config", "version": "1.0.0"}
        result = await manager.postgres_connection.execute_query(
            insert_query, "test_config", json.dumps(test_data)
        )
        assert len(result) == 1
        record_id = result[0]["id"]
        assert result[0]["key"] == "test_config"
        
        # Read
        select_query = "SELECT * FROM graph_data.metadata WHERE key = $1"
        result = await manager.postgres_connection.execute_query(
            select_query, "test_config"
        )
        assert len(result) == 1
        assert json.loads(result[0]["value"]) == test_data
        
        # Update
        update_query = """
        UPDATE graph_data.metadata
        SET value = $2, updated_at = CURRENT_TIMESTAMP
        WHERE key = $1
        RETURNING *
        """
        updated_data = {"type": "config", "version": "2.0.0"}
        result = await manager.postgres_connection.execute_query(
            update_query, "test_config", json.dumps(updated_data)
        )
        assert json.loads(result[0]["value"]) == updated_data
        
        # Delete
        delete_query = "DELETE FROM graph_data.metadata WHERE key = $1"
        await manager.postgres_connection.execute_query(delete_query, "test_config")
        
        # Verify deletion
        result = await manager.postgres_connection.execute_query(
            select_query, "test_config"
        )
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_batch_insert_neo4j(self, manager: GraphPostgresManager, clean_neo4j):
        """Neo4jのバッチインサートテスト"""
        # データを準備
        nodes = [
            {"name": f"Person_{i}", "age": 20 + i, "id": i}
            for i in range(100)
        ]
        
        # バッチインサート
        result = await manager.batch_insert_neo4j(
            label="Person",
            properties_list=nodes,
            batch_size=20
        )
        
        assert result["total_created"] == 100
        assert result["batches_processed"] == 5  # 100 / 20 = 5
        
        # 確認
        count_result = await manager.neo4j_connection.execute_query(
            "MATCH (n:Person) RETURN count(n) AS count"
        )
        assert count_result[0]["count"] == 100
    
    @pytest.mark.asyncio
    async def test_batch_insert_postgres(self, manager: GraphPostgresManager, clean_postgres):
        """PostgreSQLのバッチインサートテスト"""
        # データを準備
        data = [
            (f"key_{i}", json.dumps({"index": i, "data": f"value_{i}"}))
            for i in range(100)
        ]
        
        # バッチインサート
        result = await manager.batch_insert_postgres(
            table="graph_data.metadata",
            columns=["key", "value"],
            data=data,
            batch_size=25
        )
        
        assert result["total_inserted"] == 100
        assert result["batches_processed"] == 4  # 100 / 25 = 4
        
        # 確認
        count_result = await manager.postgres_connection.execute_query(
            "SELECT COUNT(*) AS count FROM graph_data.metadata WHERE key LIKE 'key_%'"
        )
        assert count_result[0]["count"] == 100
    
    @pytest.mark.asyncio
    async def test_large_data_handling(self, manager: GraphPostgresManager, clean_databases):
        """大量データの処理テスト"""
        # Neo4jに大量ノードを作成
        large_nodes = [
            {
                "id": i,
                "name": f"Node_{i}",
                "data": f"Some data for node {i}" * 10  # 適度なサイズのデータ
            }
            for i in range(1000)
        ]
        
        neo4j_result = await manager.batch_insert_neo4j(
            label="LargeNode",
            properties_list=large_nodes,
            batch_size=100
        )
        assert neo4j_result["total_created"] == 1000
        
        # PostgreSQLに大量データを挿入
        large_data = [
            (f"large_key_{i}", json.dumps({"id": i, "data": f"Large data {i}" * 10}))
            for i in range(1000)
        ]
        
        postgres_result = await manager.batch_insert_postgres(
            table="graph_data.metadata",
            columns=["key", "value"],
            data=large_data,
            batch_size=100
        )
        assert postgres_result["total_inserted"] == 1000
        
        # パフォーマンスを確認（基本的な閾値チェック）
        assert neo4j_result["elapsed_seconds"] < 30  # 30秒以内
        assert postgres_result["elapsed_seconds"] < 30  # 30秒以内