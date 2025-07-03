# GitHub Actions テストエラー修正依頼

## 概要
GitHub Actionsで複数のジョブが失敗しています。全てのジョブで異なるエラーが発生しており、早急な修正が必要です。

## エラー状況

### 1. Lintジョブ
- **状態**: 失敗
- **主要な問題**:
  - `N818`: Exception名に`Error`サフィックスが必要
  - `I001`: importブロックの並び順エラー
  - `UP035`, `UP006`, `UP045`: 型アノテーションの更新が必要
  - `F401`: 未使用のimport
  - `TID252`: 相対importより絶対importを使用すべき
  - `B905`: `zip()`に`strict=`パラメータが必要
  - その他多数のコード品質警告

### 2. Docker Buildジョブ
- **状態**: 失敗
- **エラー**: `Process completed with exit code 127`
- **原因**: Docker Compose設定テストの失敗

### 3. Unit Testジョブ  
- **状態**: 失敗
- **エラー**: `Process completed with exit code 1`
- **原因**: ユニットテストの実行失敗

### 4. Integration Testジョブ
- **状態**: 失敗
- **エラー**: `Process completed with exit code 1`
- **原因**: 統合テストの実行失敗

## 修正優先順位

### 優先度: 高
1. **Lint修正**
   - 例外クラス名を`GraphPostgresManagerError`に変更
   - importの整理と順序の修正
   - 型アノテーションの更新（`Dict` → `dict`、`List` → `list`など）
   - 未使用importの削除
   - 相対importを絶対importに変更

2. **テスト環境修正**
   - Docker Compose設定の確認と修正
   - テスト環境のセットアップエラーの解決

### 優先度: 中
3. **コード品質改善**
   - `zip()`に`strict=True`を追加
   - 未使用変数の削除
   - 文字列フォーマットの改善

## 影響範囲
- 全てのCI/CDパイプラインが失敗している状態
- 新しいコミットのマージが困難
- 開発効率の低下

## 推奨アクション
1. まずLintエラーを修正してコード品質を改善
2. Docker環境の設定を確認・修正
3. テストが正常に実行されるよう環境を整備
4. 全てのジョブが成功することを確認

## 参考情報
- 最新の失敗ラン: 16054423615
- 過去10回のビルドが全て失敗
- 影響を受けているブランチ: develop