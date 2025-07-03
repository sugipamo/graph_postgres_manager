"""
統合テスト用のフィクスチャとヘルパー関数
"""
import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase
from psycopg import AsyncConnection

from graph_postgres_manager import GraphPostgresManager
from graph_postgres_manager.config import ConnectionConfig


def load_test_env():
    """Load .env.test file if it exists"""
    env_file = Path(__file__).parent.parent.parent / ".env.test"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


# Load test environment variables at module import
load_test_env()


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """セッションスコープのイベントループを提供"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def get_test_config() -> ConnectionConfig:
    """テスト用の接続設定を取得"""
    # Build PostgreSQL DSN from environment variables
    postgres_user = os.getenv("POSTGRES_USER", "testuser")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "testpassword")
    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("POSTGRES_DB", "testdb")
    postgres_dsn = f"postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"
    
    return ConnectionConfig(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "testpassword")
        ),
        postgres_dsn=postgres_dsn,
    )


@pytest_asyncio.fixture
async def manager() -> AsyncGenerator[GraphPostgresManager, None]:
    """GraphPostgresManagerのインスタンスを提供"""
    config = get_test_config()
    manager = GraphPostgresManager(config)
    
    async with manager:
        yield manager


@pytest_asyncio.fixture
async def clean_neo4j(manager: GraphPostgresManager) -> AsyncGenerator[None, None]:
    """各テスト前後でNeo4jデータベースをクリーンアップ"""
    # テスト前のクリーンアップ（前回の実行データを削除）
    try:
        await manager.neo4j.execute_query("MATCH (n) DETACH DELETE n")
    except Exception:
        # エラーは無視
        pass
    
    yield
    
    # テスト後のクリーンアップ
    try:
        await manager.neo4j.execute_query("MATCH (n) DETACH DELETE n")
    except Exception:
        # エラーは無視
        pass


@pytest_asyncio.fixture
async def clean_postgres(manager: GraphPostgresManager) -> AsyncGenerator[None, None]:
    """各テスト前後でPostgreSQLデータベースをクリーンアップ"""
    # テスト前のクリーンアップ（前回の実行データを削除）
    try:
        await manager.postgres.execute_query("DELETE FROM graph_data.metadata WHERE key LIKE 'test_key_%%'")
    except Exception:
        # テーブルが存在しない場合は無視
        pass
    
    yield
    
    # テスト後のクリーンアップ
    try:
        await manager.postgres.execute_query("TRUNCATE TABLE graph_data.metadata CASCADE")
    except Exception:
        # テーブルが存在しない場合は無視
        pass


@pytest_asyncio.fixture
async def clean_databases(clean_neo4j, clean_postgres) -> AsyncGenerator[None, None]:
    """両方のデータベースをクリーンアップ"""
    yield


async def wait_for_neo4j(config: ConnectionConfig, max_retries: int = 30) -> bool:
    """Neo4jが利用可能になるまで待機"""
    for i in range(max_retries):
        try:
            driver = AsyncGraphDatabase.driver(
                config.neo4j_uri,
                auth=config.neo4j_auth
            )
            async with driver.session() as session:
                await session.run("RETURN 1")
            await driver.close()
            return True
        except Exception:
            if i < max_retries - 1:
                await asyncio.sleep(1)
            continue
    return False


async def wait_for_postgres(config: ConnectionConfig, max_retries: int = 30) -> bool:
    """PostgreSQLが利用可能になるまで待機"""
    for i in range(max_retries):
        try:
            conn = await AsyncConnection.connect(config.postgres_dsn)
            await conn.execute("SELECT 1")
            await conn.close()
            return True
        except Exception:
            if i < max_retries - 1:
                await asyncio.sleep(1)
            continue
    return False


@pytest_asyncio.fixture(scope="session", autouse=True)
async def wait_for_services(event_loop):
    """テスト実行前にサービスが利用可能になるまで待機"""
    config = get_test_config()
    
    neo4j_ready = await wait_for_neo4j(config)
    postgres_ready = await wait_for_postgres(config)
    
    if not neo4j_ready:
        pytest.fail("Neo4j service is not available")
    if not postgres_ready:
        pytest.fail("PostgreSQL service is not available")