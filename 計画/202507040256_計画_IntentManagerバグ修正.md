# IntentManagerバグ修正計画

## 作成日時
2025-07-04 02:56

## 概要
IntentManagerのPostgreSQL結果セット処理におけるタプルインデックスエラーの修正

## 現状分析

### エラー内容
- **発生箇所**: IntentManagerの4つのメソッド
  - `link_intent_to_ast` (tests/unit/intent/test_manager.py:71, 96)
  - `get_ast_nodes_by_intent` (tests/unit/intent/test_manager.py:149)
  - `search_ast_by_intent_vector` (tests/unit/intent/test_manager.py:172)
- **エラー種別**: `TypeError: tuple indices must be integers or slices, not str`
- **原因**: PostgreSQL結果セットがタプル形式で返されているが、辞書形式でアクセスしようとしている

### 影響範囲
- 138テスト中4件が失敗（失敗率: 2.9%）
- IntentManager関連の主要機能が動作不能

## 修正方針

### 1. PostgreSQL結果セットの処理方法統一
PostgresConnectionクラスの`execute`メソッドが返す結果の形式を確認し、適切にアクセスする方法に統一する。

#### 対応方法
1. **Option A**: タプルアクセスに統一
   - 各カラムをインデックスでアクセス（例: `row[0]`, `row[1]`）
   - メリット: パフォーマンスが良い
   - デメリット: コードの可読性が低下

2. **Option B**: 辞書形式への変換 【推奨】
   - `cur.description`を使用してカラム名を取得し、辞書に変換
   - メリット: コードの可読性・保守性が高い
   - デメリット: わずかなオーバーヘッド

### 2. 修正対象メソッド

#### 2.1 `link_intent_to_ast`メソッド
```python
# 現在のコード（エラー）
existing = results[0] if results else None
if existing and existing["intent_id"]:

# 修正案
existing = results[0] if results else None
if existing and existing[0]:  # または辞書変換後にアクセス
```

#### 2.2 `get_ast_nodes_by_intent`メソッド
```python
# 現在のコード（エラー）
"ast_node_id": row["ast_node_id"],

# 修正案（辞書変換後）
# PostgresConnectionで結果を辞書形式に変換するヘルパーメソッドを追加
```

#### 2.3 `search_ast_by_intent_vector`メソッド
```python
# 現在のコード（エラー）
intent_id = row["intent_id"]

# 修正案
intent_id = row[0]  # または辞書変換後にアクセス
```

### 3. PostgresConnectionクラスの改善

#### 3.1 結果セット変換ヘルパーメソッドの追加
```python
def _rows_to_dicts(self, cursor, rows):
    """Convert rows to dictionaries using cursor description."""
    if not rows or not cursor.description:
        return rows
    
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]
```

#### 3.2 executeメソッドの拡張
`return_dict`パラメータを追加して、結果形式を選択可能にする。

### 4. テストの修正
モックの返り値も実際のPostgreSQL結果セットの形式に合わせて修正する。

## 実装手順

### Phase 1: PostgresConnectionクラスの改善（30分）
1. [ ] PostgresConnectionクラスに`_rows_to_dicts`ヘルパーメソッドを追加
2. [ ] `execute`メソッドに`return_dict`パラメータを追加
3. [ ] デフォルトで辞書形式を返すように設定

### Phase 2: IntentManagerの修正（30分）
1. [ ] `link_intent_to_ast`メソッドの修正
2. [ ] `get_ast_nodes_by_intent`メソッドの修正
3. [ ] `search_ast_by_intent_vector`メソッドの修正
4. [ ] `get_intents_for_ast`メソッドの確認・修正
5. [ ] その他の影響を受けるメソッドの確認・修正

### Phase 3: テストの修正（20分）
1. [ ] モックオブジェクトの返り値を適切な形式に修正
2. [ ] テストケースの期待値を調整
3. [ ] 全てのIntentManagerテストが成功することを確認

### Phase 4: 統合テスト（20分）
1. [ ] 統合テストでの動作確認
2. [ ] 他のコンポーネントへの影響確認
3. [ ] パフォーマンステストの実施

## 成功基準
- [ ] 4件の失敗テストが全て成功
- [ ] 既存の他のテストに影響なし
- [ ] コードの可読性・保守性が向上
- [ ] パフォーマンスの劣化なし

## リスクと対策
- **リスク**: 他のコンポーネントがタプル形式を期待している可能性
- **対策**: 影響範囲を慎重に調査し、必要に応じて後方互換性を保つ

## 参考情報
- psycopgドキュメント: https://www.psycopg.org/docs/
- Python DB-API 2.0仕様: https://www.python.org/dev/peps/pep-0249/