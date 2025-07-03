# GitHub Actions Lint エラー修正依頼

作成日時: 2025-07-03 23:17

## 問題の概要

GitHub Actions の Test ワークフローで lint ジョブが失敗しています。
ruff による lint チェックで複数のコード品質問題が検出されています。

## エラー内容

### 1. 例外命名規則違反
- `src/graph_postgres_manager/exceptions.py:5:7`: N818
  - `GraphPostgresManagerException` は `Error` サフィックスが必要

### 2. 複雑度違反
- `src/graph_postgres_manager/manager.py:429:15`: PLR0912
  - `store_ast_graph` メソッドのブランチ数が多すぎる (16 > 12)
- `src/graph_postgres_manager/manager.py:577:9`: PLR0912
  - `_validate_ast_graph` メソッドのブランチ数が多すぎる (16 > 12)

### 3. 例外処理の問題
- `src/graph_postgres_manager/metadata/index_manager.py:264:9`: S110
  - try-except-pass の使用（ログ記録推奨）
- `src/graph_postgres_manager/metadata/migration.py:222:17`: B904
  - except 句内での raise に from 句が必要
- `src/graph_postgres_manager/metadata/migration.py:270:13`: B904
  - except 句内での raise に from 句が必要
- `src/graph_postgres_manager/metadata/schema_manager.py:46:13`: B904
  - except 句内での raise に from 句が必要
- `src/graph_postgres_manager/metadata/schema_manager.py:386:17`: B904
  - except 句内での raise に from 句が必要
- `src/graph_postgres_manager/metadata/schema_manager.py:456:17`: B904
  - except 句内での raise に from 句が必要

### 4. コンテキストマネージャーの推奨
- `src/graph_postgres_manager/metadata/stats_collector.py:538:17`: SIM105
  - try-except-pass の代わりに `contextlib.suppress` の使用推奨

### 5. モック実装の問題
- インポート順序とフォーマット違反
- 型アノテーションの更新が必要（Dict → dict、List → list、Optional → X | None）
- 未使用のインポート（uuid）
- 未使用の引数（database）
- __all__ のソート順

## 修正の優先順位

1. **高優先度**: 例外処理とエラーハンドリングの修正
2. **中優先度**: 型アノテーションの更新と未使用コードの削除
3. **低優先度**: 複雑度の改善とインポート順序の修正

## 推奨される対応

1. 例外クラス名を `GraphPostgresManagerError` に変更
2. 複雑なメソッドをより小さな関数に分割
3. すべての例外の再発生で `from` 句を使用
4. 型アノテーションを最新の Python 構文に更新
5. 未使用のインポートと引数を削除

## 参考リンク

- 失敗したワークフロー: https://github.com/sugipamo/graph_postgres_manager/actions/runs/16052913499