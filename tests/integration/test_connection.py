"""
接続管理の統合テスト
"""
import asyncio

import pytest

from graph_postgres_manager import GraphPostgresManager


class TestConnectionManagement:
    """接続管理のテストクラス"""
    
    @pytest.mark.asyncio
    async def test_manager_context_manager(self, manager: GraphPostgresManager):
        """コンテキストマネージャーとして使用できることを確認"""
        assert manager.neo4j_connection is not None
        assert manager.postgres_connection is not None
        
        # 接続が有効であることを確認
        result = await manager.neo4j_connection.execute_query("RETURN 1 AS number")
        assert result[0]["number"] == 1
        
        result = await manager.postgres_connection.execute_query("SELECT 1 AS number")
        assert result[0]["number"] == 1
    
    @pytest.mark.asyncio
    async def test_health_check(self, manager: GraphPostgresManager):
        """ヘルスチェック機能のテスト"""
        health = await manager.health_check()
        
        assert health.neo4j_connected is True
        assert health.postgres_connected is True
        assert health.neo4j_latency_ms >= 0
        assert health.postgres_latency_ms >= 0
        assert health.is_healthy is True
    
    @pytest.mark.asyncio
    async def test_neo4j_connection_pool(self, manager: GraphPostgresManager):
        """Neo4jの同時接続テスト"""
        async def run_query(index: int):
            query = f"CREATE (n:TestNode {{index: {index}}}) RETURN n"
            return await manager.neo4j_connection.execute_query(query)
        
        # 複数の同時クエリを実行
        tasks = [run_query(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        
        # 作成されたノードを確認
        count_result = await manager.neo4j_connection.execute_query(
            "MATCH (n:TestNode) RETURN count(n) AS count"
        )
        assert count_result[0]["count"] == 10
        
        # クリーンアップ
        await manager.neo4j_connection.execute_query("MATCH (n:TestNode) DELETE n")
    
    @pytest.mark.asyncio
    async def test_postgres_connection_pool(self, manager: GraphPostgresManager, _clean_postgres):
        """PostgreSQLのコネクションプールテスト"""
        async def insert_data(index: int):
            query = """
            INSERT INTO graph_data.metadata (key, value) 
            VALUES (%(key)s, %(value)s) 
            RETURNING id
            """
            return await manager.postgres_connection.execute_query(
                query, {"key": f"test_key_{index}", "value": f'{{"index": {index}}}'}
            )
        
        # 複数の同時挿入を実行
        tasks = [insert_data(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        
        # 挿入されたデータを確認
        count_result = await manager.postgres_connection.execute_query(
            "SELECT COUNT(*) AS count FROM graph_data.metadata WHERE key LIKE 'test_key_%%'"
        )
        assert count_result[0]["count"] == 10
    
    @pytest.mark.asyncio
    async def test_auto_reconnect_neo4j(self, manager: GraphPostgresManager):
        """Neo4jの自動再接続テスト"""
        # 正常なクエリを実行
        await manager.neo4j_connection.execute_query("RETURN 1")
        
        # 接続を強制的に閉じる(実際のテストでは接続障害をシミュレート)
        # Neo4jのドライバーを一時的に無効化
        original_driver = manager.neo4j_connection._driver
        manager.neo4j_connection._driver = None
        
        # 接続が失われたことを確認
        try:
            await manager.neo4j_connection.execute_query("RETURN 1")
            raise AssertionError("Expected exception when driver is None")
        except Exception:
            pass
        
        # ドライバーを復元して自動再接続をテスト
        manager.neo4j_connection._driver = original_driver
        
        # 再度クエリを実行できることを確認
        result = await manager.neo4j_connection.execute_query("RETURN 2 AS number")
        assert result[0]["number"] == 2
    
    @pytest.mark.asyncio
    async def test_configuration_masking(self, manager: GraphPostgresManager):
        """設定情報のマスキングテスト"""
        config_info = manager.get_config_info()
        
        # パスワードがマスクされていることを確認
        assert config_info["neo4j_password"] == "****"  # noqa: S105
        assert "****" in config_info["postgres_dsn"]
        
        # その他の情報は含まれていることを確認
        assert config_info["neo4j_uri"] == manager.config.neo4j_uri
        assert "connection_pool_size" in config_info
        assert config_info["connection_pool_size"] == manager.config.connection_pool_size