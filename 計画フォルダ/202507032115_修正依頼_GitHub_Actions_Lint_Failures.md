# GitHub Actions 修正依頼

## 発生日時
2025-07-03 21:15

## 問題の概要
GitHub ActionsのTestワークフローで継続的にlintエラーが発生しています。
最近の10回の実行のうち、9回が失敗しています。

## エラー内容

### 1. 命名規則エラー
- `GraphPostgresManagerException` クラスが `Error` サフィックスを持つべき (N818)

### 2. 複雑度エラー
- `manager.py:429` - `store_ast_graph` メソッドのブランチが多すぎる (16 > 12) (PLR0912)
- `manager.py:577` - `_validate_ast_graph` メソッドのブランチが多すぎる (16 > 12) (PLR0912)

### 3. 例外処理エラー
- 複数箇所で `raise ... from err` を使用していない (B904)
- `try-except-pass` ブロックでログ出力を推奨 (S110)
- `contextlib.suppress` の使用を推奨 (SIM105)

### 4. コードスタイルエラー
- 行の長さが100文字を超えている箇所がある (E501)
- シングルクォートとダブルクォートの混在 (Q000)
- 全角括弧の使用 (RUF003)

### 5. その他
- ループ変数の上書き (PLW2901)
- 未使用の関数引数 (ARG001)

## 修正優先度
1. **高**: 例外処理の修正（B904エラー）
2. **高**: 命名規則の修正（N818エラー）
3. **中**: 複雑度の削減（PLR0912エラー）
4. **低**: コードスタイルの統一

## 推奨される修正方法

### 1. 例外クラス名の修正
```python
# 変更前
class GraphPostgresManagerException(Exception):

# 変更後
class GraphPostgresManagerError(Exception):
```

### 2. 例外チェーンの修正
```python
# 変更前
raise SchemaError(f"Migration failed: {e}")

# 変更後
raise SchemaError(f"Migration failed: {e}") from e
```

### 3. 複雑なメソッドのリファクタリング
- `store_ast_graph` メソッドを小さなヘルパーメソッドに分割
- `_validate_ast_graph` メソッドを検証ロジックごとに分割

### 4. contextlib.suppressの使用
```python
# 変更前
try:
    await self.analyze_query_patterns()
except MetadataError:
    pass

# 変更後
import contextlib
with contextlib.suppress(MetadataError):
    await self.analyze_query_patterns()
```

## 次のステップ
1. まず高優先度のエラーから修正を開始
2. テストスイートを実行して動作確認
3. すべてのlintエラーが解消されたことを確認
4. GitHub Actionsでグリーンになることを確認