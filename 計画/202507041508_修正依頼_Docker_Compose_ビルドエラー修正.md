# 修正依頼：Docker Compose ビルドエラー修正

## 作成日時
2025年7月4日 15:08

## 問題の概要
GitHub Actions の build-docker ジョブが「Process completed with exit code 127」で失敗しています。このエラーコード127は「コマンドが見つからない」ことを示しています。

## エラーの詳細

### 1. 根本原因
`.github/workflows/test.yml` の build-docker ジョブで古い `docker-compose` コマンド（ハイフン付き）を使用していますが、GitHub Actions の Ubuntu ランナーでは新しい `docker compose`（ハイフンなし）コマンドのみが利用可能です。

### 2. 影響範囲
- GitHub Actions のビルドパイプラインが失敗
- Docker イメージのビルドとテストが実行されない
- CI/CD プロセスの一部が機能しない

## 修正内容

### 1. GitHub Actions ワークフローの修正
**ファイル**: `.github/workflows/test.yml`

**変更箇所**: build-docker ジョブ（128-142行目）

```yaml
build-docker:
  runs-on: ubuntu-latest
  steps:
  - uses: actions/checkout@v4
  
  - name: Build Docker image
    run: |
      docker build -t graph_postgres_manager:test .
  
  - name: Test Docker Compose setup
    run: |
      docker compose up -d  # docker-compose → docker compose に変更
      sleep 30  # Wait for services to be ready
      docker compose ps     # docker-compose → docker compose に変更
      docker compose down -v  # docker-compose → docker compose に変更
```

### 2. Makefile の互換性確保（オプション）
ローカル環境との互換性を保つため、Makefile でも新旧両方のコマンドをサポートすることを推奨します。

**ファイル**: `Makefile`

**変更案**:
```makefile
# Docker Compose コマンドの自動検出
DOCKER_COMPOSE := $(shell which docker-compose 2>/dev/null || echo "docker compose")

# 既存のコマンドで docker-compose を使用している箇所を $(DOCKER_COMPOSE) に置換
```

## 修正の優先度
**高**: CI/CD パイプラインの重要な部分が機能していないため、早急な修正が必要です。

## テスト方法
1. 修正後、GitHub にプッシュして Actions が正常に動作することを確認
2. ローカルで `make build` および `make test-env-up` が引き続き動作することを確認

## 関連ファイル
- `.github/workflows/test.yml`
- `Makefile`（オプション）
- `docker-compose.yml`

## 補足情報
- Docker Compose V2 では `docker-compose` コマンドが `docker compose` サブコマンドに統合されました
- GitHub Actions の Ubuntu ランナーでは Docker Compose V2 のみが利用可能です
- ローカル環境では `/snap/bin/docker-compose` が存在することを確認済み