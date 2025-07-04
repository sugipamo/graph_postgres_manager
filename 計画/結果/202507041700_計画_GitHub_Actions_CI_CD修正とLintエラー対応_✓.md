# GitHub Actions CI/CD修正とLintエラー対応計画

**作成日時**: 2025-07-04 17:00
**種別**: 実施計画
**優先度**: 高
**作業期間**: 2025-07-04 17:00 - 18:00

## 概要

GitHub ActionsのCI/CDパイプラインが複数のエラーで失敗している問題を修正し、コード品質を改善する。

## 実施内容

### 1. Docker Composeコマンドの修正 ✅
- **問題**: `docker-compose`コマンドがDocker v2で`docker compose`に変更
- **修正**: `.github/workflows/test.yml`の該当箇所を更新
- **結果**: 正常に修正完了

### 2. 統合テストfixture名の修正 ✅
- **問題**: fixture名のアンダースコアの有無による不一致
- **修正**: 
  - `_clean_neo4j` → `clean_neo4j`
  - `_clean_postgres` → `clean_postgres`
  - `_event_loop` → `event_loop`
- **結果**: 正常に修正完了

### 3. Lintエラーの修正 ✅
実施したエラー修正:

#### 高優先度
- **N818**: `ConnectionException` → `ConnectionError` (サフィックス追加)
- **A002**: ビルトイン名のシャドウイング修正
  - `id` → `result_id`
  - `type` → `result_type`
- **PLC0415**: インポート文をトップレベルに移動

#### 中優先度
- **G004**: ロギングでf-stringを使わない形式に変更
- **SIM102**: ネストしたif文を単一のif文に修正
- **PT019**: フィクスチャの使用方法を`@pytest.mark.usefixtures`に変更

### 4. その他の修正 ✅
- PLW2901: ループ変数の上書きを回避
- ARG001/ARG002: 未使用引数にコメントを追加
- S110: try-except-passにコメントを追加

## 成果

### エラー削減状況
- **修正前**: 191個のLintエラー
- **修正後**: 13個のLintエラー (93%削減)

### CI/CD修正状況
- Docker Composeコマンド: ✅ 修正完了
- 統合テストfixture: ✅ 修正完了
- PostgreSQL初期化: ✅ 確認完了

## 残課題

以下のエラーが残存しているが、次回の改善フェーズで対応予定:
- テストファイルの未使用メソッド引数
- 一部のコメント修正
- その他軽微なスタイルエラー

## 次のステップ

1. 残存する13個のLintエラーを修正
2. GitHub Actionsでのフルテスト実行を確認
3. APIドキュメント生成フェーズへ移行

## 関連ファイル

- `.github/workflows/test.yml`
- `src/graph_postgres_manager/exceptions.py`
- `src/graph_postgres_manager/mocks/manager.py`
- `src/graph_postgres_manager/mocks/data_store.py`
- `tests/integration/conftest.py`
- `tests/integration/test_data_operations.py`
- その他テストファイル

## 備考

t-wadaの推奨するテスト駆動開発の原則に従い、テスト環境の整備を最優先で実施した。