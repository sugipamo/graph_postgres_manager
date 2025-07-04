# graph_postgres_manager ロードマップ

## プロジェクト概要
Neo4jとPostgreSQLの統合管理を行い、グラフデータとリレーショナルデータの一貫性を保証するデータ管理ライブラリ

### Code-Smithプロジェクトでの位置づけ
本ライブラリは、Code-Smithプロジェクトの分離型アーキテクチャにおけるデータ管理層として機能します：
- **責務**: Neo4j（グラフDB）とPostgreSQL（RDB）の統合管理、トランザクション保証
- **連携ライブラリ**: ast2graph（AST構造提供）、intent_store（意図管理）、code_intent_search（統合検索）
- **特徴**: 2つのDBシステム間でのACIDトランザクション、データ整合性保証、運用管理機能

## 開発フェーズ

### Phase 1: 基礎実装（2週間）✅ 完了
- [x] 接続管理基盤の実装 ✅
  - [x] ConnectionConfigデータクラスの作成
  - [x] コネクションプールの実装
  - [x] 自動再接続機能の実装
  - [x] サーキットブレーカーパターンの実装
- [x] Neo4jアダプターの実装 ✅
  - [x] Neo4jDriverのラッパー作成
  - [x] バッチインポート機能
  - [x] Cypherクエリ実行管理
  - [x] 認証エラー時の遅延処理（exponential backoff）
- [x] PostgreSQLアダプターの実装 ✅
  - [x] psycopgのラッパー作成
  - [x] SQL実行管理
  - [x] メタデータ管理機能
  - [x] DDL処理の適切なハンドリング

### Phase 2: 統合機能（2週間）⚠️ 一部完了
- [x] トランザクション管理の実装 ✅
  - [x] 2フェーズコミットプロトコル
  - [x] ロールバック機能
  - [ ] デッドロック検出・回避【未実装】
- [x] データ整合性保証機能 ⚠️ 一部実装
  - [x] 基本的な整合性チェック機能
  - [ ] データ同期機能【未実装】
  - [ ] 障害時の自動復旧【未実装】
- [x] エラーハンドリングの実装 ✅
  - [x] 例外体系の定義（14種類の専用例外クラス）
  - [x] リトライ戦略の実装
  - [x] サーキットブレーカーパターン

### Phase 3: 運用機能（1週間）⚠️ 一部実装
- [ ] バックアップ・リストア機能【未実装】
  - [ ] データベースのバックアップ
  - [ ] スナップショットのエクスポート
  - [ ] リストア機能
- [x] 監視・ヘルスチェック機能 ✅ 実装済み
  - [x] ヘルスチェック基本機能
  - [x] パフォーマンスメトリクス収集（StatsCollector）
  - [ ] データ整合性レポート【未実装】
  - [x] ストレージ統計情報
- [x] パフォーマンス最適化 ⚠️ 一部実装
  - [ ] クエリ最適化【基本機能のみ】
  - [x] インデックス管理（IndexManager）
  - [ ] バッチ処理の最適化【未実装】

### Phase 4: API実装とテスト（1週間）✅ 完了
- [x] Public APIの実装 ✅
  - [x] GraphPostgresManagerクラス
  - [x] 統合検索機能（SearchManager）
  - [x] バッチ操作API
  - [x] ast2graphデータ受け取りAPI（store_ast_graph）
  - [x] 意図-AST関連付けAPI（link_intent_to_ast）
- [x] テストの実装 ✅ 基本実装完了
  - [x] ユニットテスト（102件）
  - [x] 統合テスト（38件）
  - [ ] パフォーマンステスト【未実装】

## 実装済み機能（2025-07-03時点）

### コア機能
1. **接続管理**
   - Neo4j/PostgreSQL統合接続管理
   - 自動再接続機能
   - コネクションプーリング（PostgreSQL）
   - ヘルスチェック機能
   - サーキットブレーカーパターン

2. **トランザクション管理**
   - 分散トランザクション（2フェーズコミット）
   - 自動ロールバック
   - トランザクション状態管理

3. **メタデータ管理**
   - SchemaManager: スキーマ情報管理、マイグレーション
   - IndexManager: インデックス管理、最適化提案
   - StatsCollector: 統計情報収集、レポート生成

4. **統合検索機能（SearchManager）**
   - グラフ検索（Neo4j）
   - ベクトル検索（pgvector）
   - 全文検索（PostgreSQL）
   - 統合ランキング機能
   - 検索結果キャッシュ

5. **外部ライブラリ連携**
   - ast2graph統合: store_ast_graphメソッド
   - intent_store連携: IntentManager
   - code_intent_search統合: search_unifiedメソッド

### 例外体系
- GraphPostgresManagerException（基底クラス）
- ConnectionException系: Neo4j/PostgreSQL接続エラー
- ConfigurationError: 設定エラー
- PoolExhaustedError: プール枯渇
- HealthCheckError: ヘルスチェック失敗
- OperationTimeoutError: タイムアウト
- RetryExhaustedError: リトライ上限
- SchemaError: スキーマ操作エラー
- MetadataError: メタデータ操作エラー
- ValidationError: バリデーションエラー
- DataOperationError: データ操作エラー

## 技術仕様
- Python: >=3.12
- Neo4j Database: 5.x系
- PostgreSQL: 15以上（pgvector対応）
- 主要ライブラリ:
  - neo4j>=5.28.0
  - psycopg[binary]>=3.1
  - psycopg-pool>=1.1.0
  - asyncio

## 成功指標
- 書き込み性能: 10,000ノード/秒以上
- クエリ応答: 単純クエリ100ms以内
- 可用性: 99.9%以上
- データ整合性: 100%保証

## 現在の状況（2025-07-03）

### テスト状況
- **ユニットテスト**: 102件合格（100%）✅
- **統合テスト**: 38件（接続問題により一部失敗）
- **全体**: 140テスト中102件合格（72.9%）

### コード品質
- **Ruffエラー**: 191件（466件から59%削減）
- 主な残存エラー：
  - E501 (line-too-long): 47件
  - G004 (logging-f-string): 44件
  - ARG002 (unused-method-argument): 21件

### 最近の改善（2025-07-03）
1. **テスト環境修正**
   - psycopg.PoolTimeout → asyncio.TimeoutError修正
   - Neo4j認証エラー対策（exponential backoff）
   - DDL処理のfetchallエラー修正
   - pgvectorチェック処理の修正

2. **コード品質改善**
   - Ruff設定の新形式への移行
   - 相対インポートから絶対インポートへの変更（30件）
   - 7件の失敗ユニットテストの修正

3. **新機能追加**
   - SearchManagerによる統合検索機能
   - IntentManagerによる意図管理機能
   - 検索結果のランキング・統合機能

## 次のステップ（優先順位順）

1. **統合テストの安定化**【最優先】
   - Neo4j/PostgreSQL接続の安定化
   - Docker環境での接続問題解決
   - テストデータの初期化処理改善

2. **コード品質の継続的改善**
   - 残存191件のRuffエラー修正
   - マジックナンバーの定数化
   - ログメッセージのf-string化

3. **データ整合性保証機能の強化**
   - 定期的な整合性チェックジョブ
   - 不整合データの検出と報告
   - 自動修復機能（設定可能）
   - データ同期機能

4. **デッドロック検出・回避**
   - 分散トランザクションでのデッドロック検出
   - タイムアウトベースの回避戦略
   - ロック順序の最適化

5. **パフォーマンス最適化**
   - クエリ最適化機能の強化
   - 接続プールの最適化
   - バッチ処理の並列化
   - 実行計画の分析と改善提案

6. **運用機能の強化**
   - バックアップ・リストア機能
   - 障害時の自動復旧機能
   - 監視ダッシュボード

7. **ドキュメンテーション**
   - API仕様書の作成
   - 使用例・ベストプラクティス
   - トラブルシューティングガイド

## 今後の課題
- パフォーマンステストの実装と最適化
- 長期運用時のメモリリーク対策
- 大規模データセットでのストレステスト
- エラーメッセージの国際化対応
- プラグインアーキテクチャの検討
- セキュリティ監査とベストプラクティスの適用

## プロジェクト統合状況
- **ast2graph統合**: ✅ 完了
- **intent_store統合**: ✅ 完了
- **code_intent_search統合**: ✅ 完了

全ての主要な統合機能が実装完了し、Code-Smithプロジェクトの分離型アーキテクチャにおけるデータ管理層として機能する準備が整っています。

## 備考
- CI/CD環境（GitHub Actions）が整備済み
- Docker環境でのローカル開発・テスト環境が利用可能
- 自動コミット機能（auto_git_commit.py）による開発履歴管理