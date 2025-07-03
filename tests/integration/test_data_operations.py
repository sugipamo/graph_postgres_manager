"""
データ操作の統合テスト
"""
import json

import pytest

from graph_postgres_manager import GraphPostgresManager


class TestDataOperations:
    """データ操作のテストクラス"""
    
    @pytest.mark.asyncio
    async def test_neo4j_node_crud(self, manager: GraphPostgresManager, _clean_neo4j):
        """Neo4jのノードCRUD操作テスト"""
        # Create
        create_query = """
        CREATE (n:Person {name: $name, age: $age, created_at: datetime()})
        RETURN n
        """
        result = await manager.neo4j_connection.execute_query(
            create_query, {"name": "Alice", "age": 30}
        )
        assert len(result) == 1
        assert result[0]["n"]["name"] == "Alice"
        assert result[0]["n"]["age"] == 30
        
        # Read
        read_query = "MATCH (n:Person {name: $name}) RETURN n"
        result = await manager.neo4j_connection.execute_query(read_query, {"name": "Alice"})
        assert len(result) == 1
        assert result[0]["n"]["name"] == "Alice"
        
        # Update
        update_query = """
        MATCH (n:Person {name: $name})
        SET n.age = $new_age, n.updated_at = datetime()
        RETURN n
        """
        result = await manager.neo4j_connection.execute_query(
            update_query, {"name": "Alice", "new_age": 31}
        )
        assert result[0]["n"]["age"] == 31
        
        # Delete
        delete_query = "MATCH (n:Person {name: $name}) DELETE n"
        await manager.neo4j_connection.execute_query(delete_query, {"name": "Alice"})
        
        # Verify deletion
        result = await manager.neo4j_connection.execute_query(read_query, {"name": "Alice"})
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_neo4j_relationship_crud(self, manager: GraphPostgresManager, _clean_neo4j):
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
        # リレーションシップはタプル形式で返される
        assert result[0]["a"]["name"] == "Alice"
        assert result[0]["b"]["name"] == "Bob"
        
        # Read relationship
        read_query = """
        MATCH (a:Person {name: 'Alice'})-[r:KNOWS]->(b:Person {name: 'Bob'})
        RETURN r.since as since
        """
        result = await manager.neo4j_connection.execute_query(read_query)
        assert len(result) == 1
        assert result[0]["since"] == 2020
        
        # Update relationship
        update_query = """
        MATCH (a:Person {name: 'Alice'})-[r:KNOWS]->(b:Person {name: 'Bob'})
        SET r.status = 'close_friends'
        RETURN r.status as status
        """
        result = await manager.neo4j_connection.execute_query(update_query)
        assert result[0]["status"] == "close_friends"
        
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
    async def test_postgres_crud(self, manager: GraphPostgresManager, _clean_postgres):
        """PostgreSQLのCRUD操作テスト"""
        # Create
        insert_query = """
        INSERT INTO graph_data.metadata (key, value)
        VALUES (%(key)s, %(value)s)
        RETURNING id, key, value, created_at
        """
        test_data = {"type": "config", "version": "1.0.0"}
        result = await manager.postgres_connection.execute_query(
            insert_query, {"key": "test_config", "value": json.dumps(test_data)}
        )
        assert len(result) == 1
        result[0]["id"]
        assert result[0]["key"] == "test_config"
        
        # Read
        select_query = "SELECT * FROM graph_data.metadata WHERE key = %(key)s"
        result = await manager.postgres_connection.execute_query(
            select_query, {"key": "test_config"}
        )
        assert len(result) == 1
        # PostgreSQL JSONB columns are automatically parsed to dict
        assert result[0]["value"] == test_data
        
        # Update
        update_query = """
        UPDATE graph_data.metadata
        SET value = %(value)s, updated_at = CURRENT_TIMESTAMP
        WHERE key = %(key)s
        RETURNING *
        """
        updated_data = {"type": "config", "version": "2.0.0"}
        result = await manager.postgres_connection.execute_query(
            update_query, {"key": "test_config", "value": json.dumps(updated_data)}
        )
        # PostgreSQL JSONB columns are automatically parsed to dict
        assert result[0]["value"] == updated_data
        
        # Delete
        delete_query = "DELETE FROM graph_data.metadata WHERE key = %(key)s"
        await manager.postgres_connection.execute_query(delete_query, {"key": "test_config"})
        
        # Verify deletion
        result = await manager.postgres_connection.execute_query(
            select_query, {"key": "test_config"}
        )
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_batch_insert_neo4j(self, manager: GraphPostgresManager, _clean_neo4j):
        """Neo4jのバッチインサートテスト"""
        # データを準備
        nodes = [
            {"name": f"Person_{i}", "age": 20 + i, "id": i}
            for i in range(100)
        ]
        
        # バッチインサート
        query = """
        UNWIND $nodes AS node
        CREATE (p:Person {name: node.name, age: node.age, id: node.id})
        RETURN COUNT(p) AS created
        """
        result = await manager.batch_insert_neo4j(
            query=query,
            data=[{"nodes": nodes}],
            batch_size=20
        )
        
        assert result == 100  # batch_insert_neo4j returns int, not dict
        
        # 確認
        count_result = await manager.neo4j_connection.execute_query(
            "MATCH (n:Person) RETURN count(n) AS count"
        )
        assert count_result[0]["count"] == 100
    
    @pytest.mark.asyncio
    async def test_batch_insert_postgres(self, manager: GraphPostgresManager, _clean_postgres):
        """PostgreSQLのバッチインサートテスト"""
        # データを準備
        data = [
            {"key": f"key_{i}", "value": json.dumps({"index": i, "data": f"value_{i}"})}
            for i in range(100)
        ]
        
        # バッチインサート
        query = "INSERT INTO graph_data.metadata (key, value) VALUES (%(key)s, %(value)s)"
        result = await manager.batch_insert_postgres(
            query=query,
            data=data
        )
        
        assert result == 100  # Total number of inserted rows
        
        # 確認
        count_result = await manager.postgres_connection.execute_query(
            "SELECT COUNT(*) AS count FROM graph_data.metadata WHERE key LIKE %s",
            ["key_%"]
        )
        assert count_result[0]["count"] == 100
    
    @pytest.mark.asyncio
    async def test_large_data_handling(self, manager: GraphPostgresManager, _clean_databases):
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
        
        # Use current API with query
        query = """
        UNWIND $nodes AS node
        CREATE (n:LargeNode {id: node.id, name: node.name, data: node.data})
        RETURN COUNT(n) AS created
        """
        neo4j_result = await manager.batch_insert_neo4j(
            query=query,
            data=[{"nodes": large_nodes}],
            batch_size=100
        )
        assert neo4j_result == 1000
        
        # PostgreSQLに大量データを挿入
        large_data = [
            {
                "key": f"large_key_{i}",
                "value": json.dumps({"id": i, "data": f"Large data {i}" * 10})
            }
            for i in range(1000)
        ]
        
        postgres_result = await manager.batch_insert_postgres(
            query="INSERT INTO graph_data.metadata (key, value) VALUES (%(key)s, %(value)s)",
            data=large_data
        )
        assert postgres_result == 1000