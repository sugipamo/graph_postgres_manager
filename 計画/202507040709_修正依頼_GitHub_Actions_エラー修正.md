# 202507040709_修正依頼_GitHub Actions エラー修正

## 概要
GitHub Actionsで複数のジョブが失敗しています。早急な修正が必要です。

## 問題詳細

### 1. Lint エラー (ruff)
- **ステータス**: 失敗
- **主な問題**:
  - N818: Exception名に`Error`サフィックスが必要
  - SIM105: `try-except-pass`の代わりに`contextlib.suppress`を使用
  - A002: Python組み込み名のシャドウイング (`id`, `type`)
  - PLC0415: importがトップレベルにない
  - その他多数のコード品質に関する警告

### 2. Build-Docker エラー
- **ステータス**: 失敗 (Exit code 127)
- **原因**: `docker-compose: command not found`
- **詳細**: GitHub ActionsランナーにはデフォルトでDocker Composeがインストールされていない

### 3. Integration Test エラー
- **ステータス**: 失敗
- **原因**: 上記のlintエラーとDocker環境の問題に起因

## 修正計画

### Phase 1: Docker Compose問題の修正
1. `.github/workflows/test.yml`を更新
   - `docker-compose`を`docker compose`に変更（Docker CLI統合版を使用）
   - または、`docker-compose`を明示的にインストール

### Phase 2: Lintエラーの修正
1. **例外名の修正**:
   - `GraphPostgresManagerException` → `GraphPostgresManagerError`

2. **try-except-passの修正**:
   - `contextlib.suppress`を使用するよう修正
   - 必要に応じてロギングを追加

3. **組み込み名シャドウイングの修正**:
   - `id` → `node_id`または`item_id`
   - `type` → `node_type`または`item_type`

4. **その他のコード品質問題**:
   - インポートをトップレベルに移動
   - 不要な複雑さを削減
   - 未使用の引数を適切に処理

### Phase 3: テストの再実行と確認
1. ローカルでlintとテストを実行
2. 修正をコミット
3. GitHub Actionsで確認

## 優先度
高 - CI/CDパイプラインが機能していないため、すべての開発作業に影響

## 期限
即座に対応開始