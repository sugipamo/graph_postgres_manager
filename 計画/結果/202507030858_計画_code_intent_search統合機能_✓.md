# code_intent_search統合機能の実装計画

## 概要
Code-Smithプロジェクトにおいて、code_intent_searchライブラリとの統合機能を実装する。この機能により、グラフデータベース（Neo4j）、ベクトルデータベース（pgvector）、全文検索を統合した高度な検索機能を提供する。

## 背景と目的
### 背景
- graph_postgres_managerは既にast2graphとintent_storeとの連携機能を実装済み
- code_intent_searchはこれらのデータを活用して統合検索を行うライブラリ
- 現在、統合検索APIが未実装のため、code_intent_searchから効率的にデータアクセスできない

### 目的
1. code_intent_searchが必要とする統合検索APIの提供
2. グラフ・ベクトル・全文検索の効率的な組み合わせ
3. 検索結果のランキングとスコアリング機能の実装

## 実装範囲
### 1. 統合検索APIの設計と実装
- `search_unified()` メソッドの実装
- 検索クエリの解析と最適化
- 各検索エンジンへのクエリ分配

### 2. 検索結果の統合
- Neo4jからのグラフ検索結果
- pgvectorからのベクトル類似度検索結果
- PostgreSQLからの全文検索結果
- 結果の重複排除とマージ

### 3. スコアリングとランキング
- 各検索結果のスコア正規化
- 重み付けパラメータの実装
- 最終スコアの計算とソート

### 4. パフォーマンス最適化
- 並列クエリ実行
- 結果キャッシング
- インデックス最適化の活用

## 技術仕様
### API仕様
```python
async def search_unified(
    query: str,
    vector: Optional[List[float]] = None,
    filters: Optional[Dict[str, Any]] = None,
    search_types: Optional[List[str]] = None,  # ["graph", "vector", "fulltext"]
    weights: Optional[Dict[str, float]] = None,
    limit: int = 100,
    offset: int = 0
) -> SearchResult:
    """
    統合検索を実行
    
    Args:
        query: 検索クエリ文字列
        vector: 検索ベクトル（768次元）
        filters: フィルタ条件
        search_types: 使用する検索タイプ
        weights: 各検索タイプの重み
        limit: 取得件数
        offset: オフセット
        
    Returns:
        SearchResult: 統合検索結果
    """
```

### データモデル
```python
@dataclass
class SearchResult:
    items: List[SearchResultItem]
    total_count: int
    search_time_ms: float
    metadata: Dict[str, Any]

@dataclass 
class SearchResultItem:
    id: str
    type: str  # "ast_node", "intent", etc.
    score: float
    data: Dict[str, Any]
    highlights: Optional[List[str]]
    source_scores: Dict[str, float]  # 各検索エンジンのスコア
```

## 実装ステップ
### Phase 1: 基本実装（3日）
1. SearchManagerクラスの作成
2. 基本的な統合検索メソッドの実装
3. 検索結果のデータモデル定義

### Phase 2: 検索エンジン統合（3日）
1. Neo4jグラフ検索の統合
2. pgvectorベクトル検索の統合
3. PostgreSQL全文検索の統合

### Phase 3: スコアリングとランキング（2日）
1. スコア正規化アルゴリズムの実装
2. 重み付けシステムの実装
3. ランキング機能の実装

### Phase 4: 最適化とテスト（2日）
1. 並列クエリ実行の実装
2. パフォーマンステストの作成
3. 統合テストの実装

## 成功指標
- 検索レスポンス時間: 500ms以内（95パーセンタイル）
- 検索精度: 既存の個別検索より高い関連性スコア
- スケーラビリティ: 100万件のデータでも安定動作

## リスクと対策
### リスク
1. 異なる検索エンジンのスコアの正規化が困難
2. 大量データでのパフォーマンス劣化
3. 検索結果の重複処理の複雑性

### 対策
1. 機械学習ベースのスコア調整機能を後日追加可能な設計
2. 段階的な結果取得とストリーミング対応
3. 効率的なデータ構造とアルゴリズムの採用

## 依存関係
- 既存のNeo4jConnection、PostgresConnectionクラス
- IntentManagerクラス（intent検索機能）
- IndexManager（インデックス最適化）
- TransactionManager（トランザクション管理）

## 次のアクション
1. SearchManagerクラスの基本設計
2. 検索結果データモデルの詳細設計
3. 各検索エンジンとのインターフェース設計
4. テスト戦略の策定