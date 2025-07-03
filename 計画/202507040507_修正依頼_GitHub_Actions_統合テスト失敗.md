# 202507040507_修正依頼_GitHub_Actions_統合テスト失敗

## 概要
GitHub Actionsで統合テストが継続的に失敗している問題を修正する必要があります。

## 問題詳細

### エラー内容
- **ワークフロー**: Test
- **失敗ジョブ**: integration-test
- **エラー**: Neo4j service is not available
- **失敗率**: 直近10件すべて失敗

### 根本原因
統合テスト実行時にNeo4jサービスへの接続が確立できない

```
Failed: Neo4j service is not available
tests/integration/conftest.py:161: Failed
```

## 修正内容

### 1. GitHub Actions設定の確認
- `.github/workflows/test.yml`でNeo4jサービスが正しく設定されているか確認
- サービスの起動待機時間が十分か確認

### 2. テスト環境設定の改善
- `tests/integration/conftest.py`の`wait_for_neo4j`関数の改善
  - タイムアウト時間の延長（現在の設定を確認し、必要に応じて延長）
  - リトライロジックの強化
  - より詳細なエラーログの出力

### 3. Docker Compose設定の確認
- `docker-compose.yml`のNeo4j設定確認
  - ヘルスチェック設定の追加/改善
  - 起動順序の依存関係設定

### 4. 環境変数の確認
- GitHub Actions環境でのNeo4j接続設定
  - NEO4J_URI
  - NEO4J_USER
  - NEO4J_PASSWORD

## 優先度
**高** - すべてのPRがマージできない状態のため、早急な対応が必要

## 対応予定日
2025年7月4日

## 備考
- 過去24時間で10回連続で失敗している
- ローカル環境では正常に動作することを確認済み
- GitHub Actions固有の問題の可能性が高い