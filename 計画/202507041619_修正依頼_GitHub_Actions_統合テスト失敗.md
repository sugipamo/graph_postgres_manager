# GitHub Actions統合テスト失敗の修正依頼

## 作成日時
2025年7月4日 16:19

## 問題の概要
GitHub Actionsの統合テストジョブが「Process completed with exit code 1」エラーで失敗しています。

## 詳細な調査結果

### 1. フィクスチャ名の不整合
統合テストでは以下の問題が発見されました：

1. **conftest.pyの問題**:
   - `wait_for_services`フィクスチャが存在しない`_event_loop`を参照している
   - `clean_databases`フィクスチャが存在しない`_clean_neo4j`と`_clean_postgres`を参照している

2. **テストファイルの問題**:
   - 多くのテストファイルが存在しないフィクスチャ（`_clean_postgres`, `_clean_neo4j`, `_clean_databases`）を使用している
   - 実際に定義されているのは`clean_postgres`, `clean_neo4j`, `clean_databases`（アンダースコアなし）

### 2. 影響を受けるファイル
- `tests/integration/conftest.py`
- `tests/integration/test_connection.py`
- `tests/integration/test_data_operations.py`
- その他の統合テストファイル

## 修正方針

### 1. conftest.pyの修正
```python
# 147行目の修正
@pytest_asyncio.fixture(scope="session", autouse=True)
async def wait_for_services(event_loop):  # _event_loop → event_loop に変更
    """テスト実行前にサービスが利用可能になるまで待機"""
    # ...

# 108行目の修正
@pytest_asyncio.fixture
async def clean_databases(clean_neo4j, clean_postgres) -> AsyncGenerator[None, None]:  # アンダースコアを削除
    """両方のデータベースをクリーンアップ"""
    yield
```

### 2. テストファイルの修正
すべての統合テストファイルで、フィクスチャ名から先頭のアンダースコアを削除：
- `_clean_postgres` → `clean_postgres`
- `_clean_neo4j` → `clean_neo4j`
- `_clean_databases` → `clean_databases`

### 3. 追加の修正が必要な可能性
- PostgreSQLの初期化スクリプト（`scripts/init-postgres.sql`）が正しく実行されているか確認
- テストデータベースのスキーマ（`graph_data`）が正しく作成されているか確認

## 優先度
**高** - CIパイプラインが壊れているため、即座の修正が必要

## 推定作業時間
30分

## 備考
この問題は、フィクスチャ名のリファクタリング時に一部のファイルで変更が漏れたことが原因と思われます。統一的な命名規則を維持することが重要です。