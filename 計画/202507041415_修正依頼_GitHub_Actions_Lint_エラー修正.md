# GitHub Actions Lintエラー修正依頼

**作成日時**: 2025-07-04 14:15
**種別**: 修正依頼
**優先度**: 高
**対象**: GitHub Actions CI/CD

## 概要

GitHub ActionsのLintジョブで複数のコード品質エラーが発生しています。
これらのエラーは、Pythonコーディング規約違反やセキュリティ上の懸念事項を指摘しています。

## 発生しているエラー一覧

### 1. N818: Exception命名規則違反
- **エラー**: `Exception name 'ConnectionException' should be named with an Error suffix`
- **対象ファイル**: `exceptions.py`
- **修正案**: `ConnectionException` → `ConnectionError`

### 2. PLC0415: インポート文の位置
- **エラー**: `import should be at the top-level of a file`
- **対象ファイル**: 動的インポートを使用している箇所
- **修正案**: ファイルのトップレベルにインポート文を移動

### 3. A002: ビルトイン名のシャドウイング
- **エラー**: `Function argument 'id' and 'type' are shadowing Python builtins`
- **対象ファイル**: 関数定義で`id`や`type`を引数名として使用している箇所
- **修正案**: 
  - `id` → `node_id`, `entity_id`, `item_id` など
  - `type` → `node_type`, `entity_type`, `item_type` など

### 4. G004: ロギングでのf-string使用
- **エラー**: `Logging statement uses f-string`
- **対象ファイル**: ロギング呼び出しでf-stringを使用している箇所
- **修正案**: 
  ```python
  # 修正前
  logger.info(f"Processing {item}")
  
  # 修正後
  logger.info("Processing %s", item)
  ```

### 5. SIM102: ネストしたif文
- **エラー**: `Use a single if statement instead of nested if statements`
- **対象ファイル**: 複数のif文がネストしている箇所
- **修正案**: 
  ```python
  # 修正前
  if condition1:
      if condition2:
          do_something()
  
  # 修正後
  if condition1 and condition2:
      do_something()
  ```

### 6. PT019: フィクスチャの使用方法
- **エラー**: `Fixture without value is injected as parameter, use @pytest.mark.usefixtures instead`
- **対象ファイル**: テストファイルでフィクスチャを使用している箇所
- **修正案**: 
  ```python
  # 修正前
  def test_something(setup_fixture):
      # setup_fixtureの値を使用していない
      pass
  
  # 修正後
  @pytest.mark.usefixtures("setup_fixture")
  def test_something():
      pass
  ```

### 7. S110: try-except-pass
- **エラー**: `try-except-pass detected, consider logging the exception`
- **対象ファイル**: 例外を無視している箇所
- **修正案**: 
  ```python
  # 修正前
  try:
      do_something()
  except Exception:
      pass
  
  # 修正後
  try:
      do_something()
  except Exception as e:
      logger.debug("Operation failed: %s", e)
  ```

### 8. RUF002: あいまいな文字
- **エラー**: `Docstring contains ambiguous character`
- **対象ファイル**: ドキュメント文字列に特殊文字が含まれている箇所
- **修正案**: 全角文字や特殊なUnicode文字を半角ASCII文字に置換

## 修正優先順位

1. **高優先度**（機能に影響する可能性）
   - A002: ビルトイン名のシャドウイング
   - PLC0415: インポート文の位置
   - N818: Exception命名規則

2. **中優先度**（コード品質）
   - SIM102: ネストしたif文
   - G004: ロギングでのf-string使用
   - PT019: フィクスチャの使用方法

3. **低優先度**（スタイル）
   - S110: try-except-pass
   - RUF002: あいまいな文字

## 修正アプローチ

1. 各エラーが発生している具体的なファイルと行番号を特定
2. エラーごとに修正を実施
3. 修正後、ローカルでlintチェックを実行して確認
4. すべてのエラーが解消されたらコミット

## 次のステップ

1. `make lint`コマンドでローカル環境でエラーを再現
2. 上記の修正案に従って各エラーを修正
3. 修正完了後、再度`make lint`で確認
4. GitHub Actionsでの動作確認

## 関連ファイル

- `.github/workflows/`内のワークフローファイル
- `pyproject.toml`（lint設定）
- 各エラーが発生しているソースファイル