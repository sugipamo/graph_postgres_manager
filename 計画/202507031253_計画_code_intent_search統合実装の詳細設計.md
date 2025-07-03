# code_intent_search統合実装の詳細設計

## 概要
graph_postgres_managerにcode_intent_searchライブラリとの統合機能を実装し、Code-Smithプロジェクトの統合検索インターフェースを提供する。

## 実装目標
- SearchManagerクラスの実装
- search_unifiedメソッドの実装（GraphPostgresManagerのPublic API）
- グラフ検索、ベクトル検索、全文検索の統合
- 検索結果のランキングとスコアリング機能
- Code-Smithプロジェクトの他のコンポーネントとのシームレスな連携

## 詳細設計

### 1. SearchManagerクラスの設計

```python
# src/graph_postgres_manager/search/manager.py
class SearchManager:
    def __init__(self, neo4j_conn: Neo4jConnection, postgres_conn: PostgresConnection):
        """検索マネージャーの初期化"""
        pass
    
    async def search_graph(self, query: GraphQuery) -> List[GraphResult]:
        """グラフベースの検索（Neo4j）"""
        pass
    
    async def search_vector(self, vector: List[float], threshold: float = 0.8) -> List[VectorResult]:
        """ベクトルベースの検索（pgvector）"""
        pass
    
    async def search_fulltext(self, text: str, filters: Dict[str, Any]) -> List[TextResult]:
        """全文検索（PostgreSQL）"""
        pass
    
    async def combine_results(self, results: Dict[str, List[Any]]) -> List[UnifiedResult]:
        """検索結果の統合とランキング"""
        pass
```

### 2. 統合検索APIの設計

```python
# GraphPostgresManagerへの追加メソッド
async def search_unified(
    self,
    query: Optional[str] = None,
    vector: Optional[List[float]] = None,
    graph_pattern: Optional[Dict[str, Any]] = None,
    search_type: SearchType = SearchType.ALL,
    limit: int = 100,
    offset: int = 0
) -> SearchResults:
    """
    統合検索機能
    
    Args:
        query: テキスト検索クエリ
        vector: ベクトル検索用の埋め込みベクトル
        graph_pattern: グラフパターンマッチング用のパターン
        search_type: 検索タイプ（GRAPH, VECTOR, TEXT, ALL）
        limit: 結果の最大数
        offset: オフセット（ページネーション用）
    
    Returns:
        SearchResults: 統合された検索結果
    """
    pass
```

### 3. データモデルの設計

```python
# src/graph_postgres_manager/search/models.py
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional

class SearchType(Enum):
    GRAPH = "graph"
    VECTOR = "vector"
    TEXT = "text"
    ALL = "all"

@dataclass
class SearchResults:
    """統合検索結果"""
    total_count: int
    results: List['UnifiedResult']
    search_time_ms: float
    metadata: Dict[str, Any]

@dataclass
class UnifiedResult:
    """個別の検索結果"""
    id: str
    type: str  # "ast_node", "intent", "code_block" など
    score: float  # 0.0-1.0の正規化されたスコア
    source: SearchType  # どの検索エンジンから来たか
    data: Dict[str, Any]  # 実際のデータ
    highlights: Optional[Dict[str, List[str]]] = None  # ハイライト情報
```

### 4. スコアリングアルゴリズム

```python
class ScoreCalculator:
    """検索結果のスコア計算"""
    
    def calculate_composite_score(
        self,
        graph_score: Optional[float] = None,
        vector_score: Optional[float] = None,
        text_score: Optional[float] = None,
        weights: Dict[str, float] = None
    ) -> float:
        """
        複合スコアの計算
        デフォルトの重み:
        - グラフ: 0.4
        - ベクトル: 0.4
        - テキスト: 0.2
        """
        pass
```

### 5. 実装手順

1. **検索モデルの定義** (search/models.py)
   - SearchType、SearchResults、UnifiedResultなどのデータクラス
   - 検索クエリの型定義

2. **SearchManagerクラスの実装** (search/manager.py)
   - 各検索エンジンへのクエリ実行
   - 結果の正規化とマージ
   - スコアリング機能

3. **GraphPostgresManagerへの統合**
   - search_unifiedメソッドの追加
   - SearchManagerのインスタンス管理
   - エラーハンドリング

4. **テストの実装**
   - 単体テスト（各検索機能）
   - 統合テスト（結果の統合）
   - パフォーマンステスト

### 6. code_intent_searchとの連携

```python
# Code-Smithプロジェクトでの使用例
from graph_postgres_manager import GraphPostgresManager

async def search_code_with_intent(query: str, intent_vector: List[float]):
    """コードと意図を組み合わせた検索"""
    async with GraphPostgresManager(config) as manager:
        results = await manager.search_unified(
            query=query,
            vector=intent_vector,
            search_type=SearchType.ALL
        )
        return results
```

### 7. パフォーマンス考慮事項

- 並列クエリ実行（asyncio.gather）
- 結果のキャッシング（Redis連携も検討）
- インデックスの最適化
- クエリプランの分析と改善

### 8. エラーハンドリング

- 個別の検索エンジンの障害に対する耐性
- 部分的な結果の返却（一部の検索エンジンが失敗しても継続）
- タイムアウト処理
- リトライ戦略

## 成功基準

- 統合検索の応答時間: 500ms以内（通常のクエリ）
- 検索精度: 関連性スコア0.8以上の結果が上位に
- 可用性: 個別エンジンの障害時も部分的に動作
- スケーラビリティ: 100万件のデータでも性能維持

## 実装期間見積もり

- 基本実装: 3-4日
- テスト実装: 2日
- 最適化とチューニング: 2日
- ドキュメント作成: 1日

合計: 約1週間

## 次のステップ

1. この設計書のレビューと承認
2. SearchManagerクラスの基本実装開始
3. 各検索エンジンとの統合実装
4. テストとパフォーマンスチューニング
5. Code-Smithプロジェクトとの統合テスト