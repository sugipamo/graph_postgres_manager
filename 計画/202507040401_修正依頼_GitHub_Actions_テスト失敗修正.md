# 202507040401_修正依頼_GitHub_Actions_テスト失敗修正

## 概要
GitHub ActionsのTest workflowで複数のジョブが失敗しています。主な問題は以下の通りです：

## 失敗しているジョブ

### 1. unit-test
- **エラー**: テストケースの失敗
- **失敗箇所**:
  - `tests/unit/search/test_manager.py::TestSearchManager::test_text_search`
  - `tests/unit/search/test_manager.py::TestSearchManager::test_unified_search`
- **原因**: MockオブジェクトがAsyncコンテキストで正しく設定されていない

### 2. build-docker
- **エラー**: docker-compose downコマンドが見つからない (exit code 127)
- **原因**: docker-composeがインストールされていない、またはPATHに存在しない

### 3. integration-test
- **エラー**: 統合テストの失敗
- **原因**: 詳細なログ確認が必要

### 4. lint
- **エラー**: Ruffによるリントエラー
- **原因**: コード品質の問題

## 修正方針

### 1. 単体テストの修正
```python
# tests/unit/search/test_manager.pyの修正
# MagicMockの代わりにAsyncMockを適切に使用する
mock_postgres_connection.get_connection = AsyncMock(return_value=mock_context)
```

### 2. Docker Composeの修正
```yaml
# .github/workflows/test.ymlの修正
# docker-composeコマンドをdocker composeに変更
- name: Test Docker Compose setup
  run: |
    docker compose down || true
    docker compose up -d
```

### 3. Lintエラーの修正
- Ruffのエラーメッセージを確認して、コード品質の問題を修正

### 4. 統合テストの修正
- 詳細なエラーログを確認して、適切な修正を実施

## 優先順位
1. Lintエラーの修正（最も基本的な問題）
2. 単体テストの修正（モックの設定）
3. Docker Composeの修正（CI環境の設定）
4. 統合テストの修正（環境依存の問題）

## 次のステップ
1. 各エラーの詳細を確認
2. 修正を実装
3. ローカルでテストを実行して確認
4. プルリクエストを作成