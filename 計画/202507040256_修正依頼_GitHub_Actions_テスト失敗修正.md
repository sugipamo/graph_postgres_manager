# GitHub Actions テスト失敗修正依頼

## 問題の概要
GitHub Actionsの統合テストで `intent_ast_map` テーブルが存在しないエラーが発生しています。

## エラー詳細
```
psycopg.errors.UndefinedTable: relation "intent_ast_map" does not exist
```

## 影響範囲
- test_intent_ast_lifecycle
- test_intent_vector_search  
- test_intent_with_unified_search
- test_concurrent_intent_operations

## 根本原因
PostgreSQLのテーブル初期化スクリプト(`scripts/init-postgres.sql`)に`intent_ast_map`テーブルの定義が含まれていない。

## 修正方針
1. `scripts/init-postgres.sql`に`intent_ast_map`テーブルの定義を追加
2. 必要なインデックスも含める
3. GitHub Actionsのワークフローで正しくスクリプトが実行されることを確認

## 優先度
高 - すべてのCIビルドが失敗している状態

## 期限
即時対応が必要