# 修正依頼: ConnectionError例外クラスの未定義エラー修正

## 概要
GitHub Actionsのテストで `ImportError: cannot import name 'ConnectionError' from 'graph_postgres_manager'` エラーが発生しています。

## 問題の詳細
- ファイル: `tests/test_exceptions.py`
- エラー内容: `ConnectionError` クラスが `graph_postgres_manager` パッケージからインポートできない
- 最新の実行ID: 16067343609
- 発生時刻: 2025-07-04T06:27:57Z

## エラーログ
```
tests/test_exceptions.py:5: in <module>
    from graph_postgres_manager import (
E   ImportError: cannot import name 'ConnectionError' from 'graph_postgres_manager' (/home/runner/work/graph_postgres_manager/graph_postgres_manager/src/graph_postgres_manager/__init__.py). Did you mean: 'ConnectionState'?
```

## 修正内容
1. `src/graph_postgres_manager/__init__.py` に `ConnectionError` クラスのエクスポートを追加する
2. または、`ConnectionError` クラスの定義自体が欠落している場合は、適切な例外クラスを実装する
3. テストファイルで使用されている例外クラス名が正しいか確認する

## 影響範囲
- 全てのGitHub Actionsのテスト実行が失敗している（過去10回全て失敗）
- 単体テストが実行できないため、コードの品質保証ができない状態

## 優先度
高 - CI/CDパイプラインが完全に機能していないため、早急な修正が必要