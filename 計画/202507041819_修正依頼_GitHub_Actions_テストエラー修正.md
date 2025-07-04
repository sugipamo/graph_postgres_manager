# 202507041819_修正依頼_GitHub_Actions_テストエラー修正

## 概要
GitHub Actionsで以下のエラーが発生しています：
- **unit-test**: `ConnectionError`のインポートエラー
- **lint**: インポート順序、未使用引数、セキュリティ警告など
- **integration-test**: テスト実行時のエラー

## エラー詳細

### 1. unit-testの失敗
```
ImportError: cannot import name 'ConnectionError' from 'graph_postgres_manager'
```
- `tests/test_exceptions.py`が存在しない`ConnectionError`をインポートしようとしている
- 正しくは`GraphConnectionError`、`Neo4jConnectionError`、`PostgresConnectionError`のいずれか

### 2. lintエラー
主要なエラー：
- `src/graph_postgres_manager/__init__.py`: インポート順序と`__all__`のソート
- 複数ファイル: 未使用の関数引数（ARG001, ARG002）
- `tests/integration/test_connection.py`: `try-except-pass`のセキュリティ警告（S110）
- `tests/test_exceptions.py`: Python組み込みの`ConnectionError`をシャドウイング（A004）

### 3. integration-testの失敗
詳細ログが必要ですが、unit-testとlintの修正後に再確認が必要

## 修正優先順位
1. **高**: `ConnectionError`インポートエラーの修正
2. **高**: `__init__.py`のインポート順序とエクスポート順序
3. **中**: Lintエラー（未使用引数、セキュリティ警告など）

## 対応方針
1. `tests/test_exceptions.py`で正しいエラークラス名を使用
2. `__init__.py`のインポートとエクスポートをアルファベット順にソート
3. 未使用引数にアンダースコアプレフィックスを追加またはnoqa指定
4. セキュリティ警告には適切なロギングまたはnoqa指定を追加