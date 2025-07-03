# MockGraphPostgresManager 使用ガイド

## 概要

`MockGraphPostgresManager`は、`GraphPostgresManager`の完全なモック実装です。実際のNeo4jやPostgreSQLサーバーへの接続を必要とせず、テスト環境で使用できます。

### 特徴

- **ゼロ依存**: Python標準ライブラリのみを使用
- **完全インメモリ**: 全データはメモリ上に保存
- **高速動作**: ネットワークI/Oなし、ミリ秒単位の応答
- **API互換**: 本番実装と100%同じインターフェース
- **テスト支援機能**: 呼び出し履歴、アサーション機能など

## インストール

モック実装は`graph_postgres_manager`パッケージに含まれています：

```python
from graph_postgres_manager.mocks import MockGraphPostgresManager
```

## 基本的な使用方法

### 1. シンプルな使用例

```python
import asyncio
from graph_postgres_manager.mocks import MockGraphPostgresManager

async def test_basic_usage():
    # モックマネージャーの作成
    async with MockGraphPostgresManager() as manager:
        # Neo4jクエリの実行
        result = await manager.execute_neo4j_query(
            "CREATE (n:Person {name: $name}) RETURN n",
            {"name": "Alice"}
        )
        print(f"Created node: {result}")
        
        # PostgreSQLクエリの実行
        await manager.execute_postgres_query(
            "CREATE TABLE users (id INTEGER, name TEXT)"
        )
        
        await manager.execute_postgres_query(
            "INSERT INTO users VALUES (1, 'Alice')"
        )

# 実行
asyncio.run(test_basic_usage())
```

### 2. ASTグラフの保存

```python
async def test_ast_storage():
    async with MockGraphPostgresManager() as manager:
        # AST2Graphからの出力を模したデータ
        graph_data = {
            "nodes": [
                {
                    "id": "func_1",
                    "labels": ["Function"],
                    "properties": {
                        "name": "calculate_sum",
                        "line_start": 10,
                        "line_end": 15
                    }
                },
                {
                    "id": "param_1",
                    "labels": ["Parameter"],
                    "properties": {
                        "name": "numbers",
                        "type": "List[int]"
                    }
                }
            ],
            "edges": [
                {
                    "source": "func_1",
                    "target": "param_1",
                    "type": "HAS_PARAMETER"
                }
            ]
        }
        
        # グラフデータの保存
        result = await manager.store_ast_graph(
            graph_data,
            source_id="calculator.py",
            metadata={"version": "1.0"}
        )
        
        print(f"Stored {result['nodes_created']} nodes and {result['edges_created']} edges")
```

### 3. 統合検索

```python
async def test_unified_search():
    async with MockGraphPostgresManager() as manager:
        # データの準備
        graph_data = {
            "nodes": [
                {"id": "1", "labels": ["Function"], "properties": {"name": "process_data"}},
                {"id": "2", "labels": ["Function"], "properties": {"name": "validate_data"}},
                {"id": "3", "labels": ["Class"], "properties": {"name": "DataProcessor"}}
            ],
            "edges": []
        }
        
        await manager.store_ast_graph(graph_data, "processor.py")
        
        # 検索実行
        results = await manager.search_unified(
            "data",  # "data"を含む全ての要素を検索
            include_graph=True,
            include_text=True,
            max_results=10
        )
        
        print(f"Found {len(results)} results")
        for result in results:
            print(f"  - {result.data['properties']['name']} (score: {result.score})")
```

### 4. トランザクション管理

```python
async def test_transactions():
    async with MockGraphPostgresManager() as manager:
        try:
            # トランザクション開始
            async with manager.transaction() as tx:
                # Neo4jとPostgreSQLの操作
                await manager.execute_neo4j_query("CREATE (n:Node {id: 1})")
                await manager.execute_postgres_query("INSERT INTO logs VALUES (1, 'created')")
                
                # 自動的にコミットされる
        except Exception as e:
            print(f"Transaction failed: {e}")
            # 自動的にロールバックされる
```

## テスト支援機能

### 1. 設定のカスタマイズ

```python
# レイテンシやエラー率の設定
config = {
    "neo4j_latency": 10,      # Neo4j操作の遅延（ミリ秒）
    "postgres_latency": 5,     # PostgreSQL操作の遅延（ミリ秒）
    "error_rate": 0.1,         # エラー発生率（0.0-1.0）
    "max_connections": 50,     # 最大接続数
    "health_check_interval": 1.0  # ヘルスチェック間隔（秒）
}

manager = MockGraphPostgresManager(config)
```

### 2. 呼び出し履歴の確認

```python
async def test_call_tracking():
    async with MockGraphPostgresManager() as manager:
        # いくつかの操作を実行
        await manager.execute_neo4j_query("MATCH (n) RETURN n")
        await manager.store_ast_graph({"nodes": [], "edges": []}, "test.py")
        
        # 呼び出し履歴を取得
        history = manager.get_call_history()
        
        for call in history:
            print(f"{call['method']} was called with {call['args']}")
        
        # 特定のクエリが呼ばれたか確認
        assert manager.assert_query_called("MATCH (n)")
```

### 3. データのクリア

```python
async def test_data_isolation():
    manager = MockGraphPostgresManager()
    await manager.initialize()
    
    # テスト1
    await manager.execute_neo4j_query("CREATE (n:TestNode)")
    stats = manager.get_mock_stats()
    print(f"Nodes after test 1: {stats['nodes_count']}")
    
    # データをクリア
    manager.clear_data()
    
    # テスト2（クリーンな状態から開始）
    stats = manager.get_mock_stats()
    print(f"Nodes after clear: {stats['nodes_count']}")  # 0
    
    await manager.close()
```

### 4. 統計情報の取得

```python
async def test_statistics():
    async with MockGraphPostgresManager() as manager:
        # 様々な操作を実行
        for i in range(10):
            await manager.execute_neo4j_query(f"CREATE (n:Node {{id: {i}}})")
        
        # 統計情報を取得
        stats = manager.get_mock_stats()
        print(f"Total nodes: {stats['nodes_count']}")
        print(f"Total queries: {stats['query_count']}")
        print(f"Average operation time: {stats['avg_operation_time']:.3f}s")
```

## 実際のテストでの使用例

### pytestでの使用

```python
import pytest
from graph_postgres_manager.mocks import MockGraphPostgresManager

@pytest.fixture
async def mock_manager():
    """モックマネージャーのフィクスチャ"""
    manager = MockGraphPostgresManager()
    await manager.initialize()
    yield manager
    await manager.close()

@pytest.mark.asyncio
async def test_my_function(mock_manager):
    """実際のテスト関数"""
    # mock_managerを使用したテスト
    result = await my_function_that_uses_manager(mock_manager)
    assert result.success
    
    # 期待される呼び出しを確認
    assert mock_manager.assert_query_called("CREATE")
```

### 本番コードとの切り替え

```python
import os

async def get_manager():
    """環境に応じてマネージャーを返す"""
    if os.getenv("USE_MOCK", "false").lower() == "true":
        from graph_postgres_manager.mocks import MockGraphPostgresManager
        return MockGraphPostgresManager()
    else:
        from graph_postgres_manager import GraphPostgresManager
        from graph_postgres_manager.config import ConnectionConfig
        return GraphPostgresManager(ConnectionConfig())

# 使用
async def main():
    async with await get_manager() as manager:
        # managerを使用した処理
        pass
```

## 制限事項

1. **部分的なクエリサポート**: CypherやSQLの完全なパーサーは実装していません
2. **メモリ制限**: 大量のデータを扱う場合はメモリ使用量に注意
3. **永続性なし**: プロセス終了時に全データが失われます
4. **単純な検索**: 複雑な検索条件は限定的なサポート

## ベストプラクティス

1. **テスト間でのデータ分離**: 各テストの前後で`clear_data()`を呼ぶ
2. **適切な遅延設定**: 実環境に近い遅延を設定してテスト
3. **アサーション活用**: `assert_query_called()`等を使用して期待される動作を確認
4. **統計情報の確認**: パフォーマンステストでは統計情報を活用

## まとめ

`MockGraphPostgresManager`は、テスト環境での開発を大幅に簡素化します。実際のデータベースサーバーのセットアップや管理が不要で、高速かつ確実なテストが可能です。