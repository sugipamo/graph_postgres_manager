# graph_postgres_manager

Neo4jとPostgreSQLの統合管理を行い、グラフデータとリレーショナルデータの一貫性を保証するデータ管理ライブラリ。

## 概要

graph_postgres_managerは、Code-Smithプロジェクトの一部として開発された、Neo4jとPostgreSQLの両データベースを統合的に管理するPythonライブラリです。

### 主な特徴

- **統合管理**: Neo4jとPostgreSQLの接続管理を一元化
- **分散トランザクション管理**: 両DB間でのトランザクション整合性保証（2フェーズコミット対応）
- **自動再接続**: 接続障害時の自動リトライとフェイルオーバー
- **ヘルスチェック**: 定期的な接続状態監視と自動復旧
- **コネクションプーリング**: PostgreSQL接続の効率的な管理
- **バッチ操作**: 大量データの効率的な一括処理
- **非同期処理**: asyncioベースの高速処理

## インストール

```bash
pip install graph-postgres-manager
```

## 使用方法

```python
from graph_postgres_manager import GraphPostgresManager, ConnectionConfig

# 設定
config = ConnectionConfig(
    neo4j_uri="bolt://localhost:7687",
    neo4j_auth=("neo4j", "password"),
    postgres_dsn="postgresql://user:pass@localhost/dbname"
)

# マネージャー初期化
async with GraphPostgresManager(config) as manager:
    # 基本的なクエリ実行
    neo4j_result = await manager.execute_neo4j_query(
        "MATCH (n:Node) RETURN n LIMIT 10"
    )
    postgres_result = await manager.execute_postgres_query(
        "SELECT * FROM nodes LIMIT 10"
    )
    
    # トランザクション管理
    async with manager.transaction() as tx:
        # Neo4jとPostgreSQLの操作を一つのトランザクションで実行
        await tx.neo4j_execute(
            "CREATE (n:User {id: $id, name: $name})",
            {"id": 1, "name": "Alice"}
        )
        await tx.postgres_execute(
            "INSERT INTO users (id, name) VALUES ($1, $2)",
            [1, "Alice"]
        )
        # エラーが発生すると自動的にロールバック
    
    # バッチ操作
    nodes_data = [{"id": i, "value": f"node_{i}"} for i in range(1000)]
    await manager.batch_insert_neo4j(
        "CREATE (n:Node {id: row.id, value: row.value})",
        nodes_data
    )
```

## 要件

- Python >= 3.12
- Neo4j >= 5.x
- PostgreSQL >= 15

## ライセンス

MIT License