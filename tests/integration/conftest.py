"""
統合テスト用のフィクスチャとヘルパー関数
"""
import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase
from psycopg import AsyncConnection

from graph_postgres_manager import GraphPostgresManager
from graph_postgres_manager.config import ConnectionConfig


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """セッションスコープのイベントループを提供"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def get_test_config() -> ConnectionConfig:
    """テスト用の接続設定を取得"""
    return ConnectionConfig(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "testpassword"),
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DB", "testdb"),
        postgres_user=os.getenv("POSTGRES_USER", "testuser"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "testpassword"),
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
    yield
    
    # テスト後のクリーンアップ
    async with manager.neo4j_connection.get_session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest_asyncio.fixture
async def clean_postgres(manager: GraphPostgresManager) -> AsyncGenerator[None, None]:
    """各テスト前後でPostgreSQLデータベースをクリーンアップ"""
    yield
    
    # テスト後のクリーンアップ
    async with manager.postgres_connection.get_connection() as conn:
        await conn.execute("TRUNCATE TABLE graph_data.metadata CASCADE")


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
                auth=(config.neo4j_user, config.neo4j_password)
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
            conn = await AsyncConnection.connect(
                host=config.postgres_host,
                port=config.postgres_port,
                dbname=config.postgres_database,
                user=config.postgres_user,
                password=config.postgres_password,
            )
            await conn.execute("SELECT 1")
            await conn.close()
            return True
        except Exception:
            if i < max_retries - 1:
                await asyncio.sleep(1)
            continue
    return False


@pytest.fixture(scope="session", autouse=True)
async def wait_for_services(event_loop):
    """テスト実行前にサービスが利用可能になるまで待機"""
    config = get_test_config()
    
    neo4j_ready = await wait_for_neo4j(config)
    postgres_ready = await wait_for_postgres(config)
    
    if not neo4j_ready:
        pytest.fail("Neo4j service is not available")
    if not postgres_ready:
        pytest.fail("PostgreSQL service is not available")