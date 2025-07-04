import asyncio
from unittest.mock import AsyncMock

import pytest

from graph_postgres_manager.connections.neo4j import Neo4jConnection
from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.transactions.manager import (
    TransactionContext,
    TransactionError,
    TransactionManager,
    TransactionRollbackError,
    TransactionState,
)


class TestTransactionManager:
    """TransactionManagerクラスのテスト"""

    @pytest.fixture
    def mock_neo4j_connection(self):
        """Neo4j接続のモック"""
        mock = AsyncMock(spec=Neo4jConnection)
        mock.execute_query = AsyncMock()
        mock.begin_transaction = AsyncMock()
        mock.commit_transaction = AsyncMock()
        mock.rollback_transaction = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres_connection(self):
        """PostgreSQL接続のモック"""
        mock = AsyncMock(spec=PostgresConnection)
        mock.execute = AsyncMock()
        mock.begin_transaction = AsyncMock()
        mock.commit_transaction = AsyncMock()
        mock.rollback_transaction = AsyncMock()
        return mock

    @pytest.fixture
    def transaction_manager(self, mock_neo4j_connection, mock_postgres_connection):
        """TransactionManagerのインスタンス"""
        return TransactionManager(
            neo4j_connection=mock_neo4j_connection,
            postgres_connection=mock_postgres_connection
        )

    @pytest.mark.asyncio
    async def test_transaction_context_success(self, transaction_manager):
        """正常なトランザクションのテスト"""
        async with transaction_manager.transaction() as ctx:
            assert isinstance(ctx, TransactionContext)
            assert ctx.state == TransactionState.ACTIVE
            
            # トランザクション内での操作
            await ctx.neo4j_execute("MATCH (n) RETURN n")
            await ctx.postgres_execute("SELECT * FROM users")
        
        # トランザクションが正常にコミットされたことを確認
        assert ctx.state == TransactionState.COMMITTED
        transaction_manager.neo4j_connection.commit_transaction.assert_called_once()
        transaction_manager.postgres_connection.commit_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, transaction_manager):
        """エラー時のロールバックテスト"""
        transaction_manager.neo4j_connection.execute_query.side_effect = Exception("Query failed")
        
        with pytest.raises(Exception, match="Query failed"):
            async with transaction_manager.transaction() as ctx:
                await ctx.neo4j_execute("INVALID QUERY")
        
        # ロールバックが呼ばれたことを確認
        assert ctx.state == TransactionState.ROLLED_BACK
        transaction_manager.neo4j_connection.rollback_transaction.assert_called_once()
        transaction_manager.postgres_connection.rollback_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_rollback(self, transaction_manager):
        """手動ロールバックのテスト"""
        async with transaction_manager.transaction() as ctx:
            await ctx.neo4j_execute("MATCH (n) RETURN n")
            await ctx.rollback()
            assert ctx.state == TransactionState.ROLLED_BACK
        
        # ロールバックが呼ばれ、コミットが呼ばれていないことを確認
        transaction_manager.neo4j_connection.rollback_transaction.assert_called_once()
        transaction_manager.postgres_connection.rollback_transaction.assert_called_once()
        transaction_manager.neo4j_connection.commit_transaction.assert_not_called()
        transaction_manager.postgres_connection.commit_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_nested_transactions(self, transaction_manager):
        """ネストされたトランザクションのテスト"""
        async with transaction_manager.transaction() as outer_ctx:
            await outer_ctx.neo4j_execute("OUTER QUERY")
            
            async with transaction_manager.transaction() as inner_ctx:
                await inner_ctx.neo4j_execute("INNER QUERY")
                assert inner_ctx.is_nested
            
            assert outer_ctx.state == TransactionState.ACTIVE
        
        assert outer_ctx.state == TransactionState.COMMITTED

    @pytest.mark.asyncio
    async def test_two_phase_commit(self, transaction_manager):
        """2フェーズコミットのテスト"""
        transaction_manager.enable_two_phase_commit = True
        
        async with transaction_manager.transaction() as ctx:
            await ctx.neo4j_execute("MATCH (n) RETURN n")
            await ctx.postgres_execute("SELECT * FROM users")
        
        # prepare と commit の両方が呼ばれることを確認
        transaction_manager.neo4j_connection.prepare_transaction.assert_called_once()
        transaction_manager.postgres_connection.prepare_transaction.assert_called_once()
        transaction_manager.neo4j_connection.commit_prepared.assert_called_once()
        transaction_manager.postgres_connection.commit_prepared.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_failure_handling(self, transaction_manager):
        """ロールバック失敗時の処理テスト"""
        transaction_manager.neo4j_connection.execute_query.side_effect = Exception("Query failed")
        transaction_manager.postgres_connection.rollback_transaction.side_effect = (
            Exception("Rollback failed")
        )
        
        with pytest.raises(TransactionRollbackError):
            async with transaction_manager.transaction() as ctx:
                await ctx.neo4j_execute("INVALID QUERY")

    @pytest.mark.asyncio
    async def test_transaction_timeout(self, transaction_manager):
        """トランザクションタイムアウトのテスト"""
        async def slow_query(*_args, **_kwargs):
            await asyncio.sleep(2)
            return []
        
        transaction_manager.neo4j_connection.execute_query.side_effect = slow_query
        
        with pytest.raises(asyncio.TimeoutError):
            async with transaction_manager.transaction(timeout=1) as ctx:
                await ctx.neo4j_execute("SLOW QUERY")
        
        # タイムアウト時にロールバックされることを確認
        assert ctx.state == TransactionState.ROLLED_BACK

    @pytest.mark.asyncio
    async def test_concurrent_transactions(self, transaction_manager):
        """同時実行トランザクションのテスト"""
        results = []
        
        async def transaction_task(task_id):
            async with transaction_manager.transaction() as ctx:
                await ctx.neo4j_execute(f"QUERY {task_id}")
                results.append(task_id)
        
        # 複数のトランザクションを同時実行
        await asyncio.gather(
            transaction_task(1),
            transaction_task(2),
            transaction_task(3)
        )
        
        assert len(results) == 3
        assert set(results) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_transaction_state_transitions(self, transaction_manager):
        """トランザクション状態遷移のテスト"""
        ctx = TransactionContext(
            transaction_manager,
            transaction_id="test-123",
            is_nested=False
        )
        
        # 初期状態
        assert ctx.state == TransactionState.PENDING
        
        # 開始
        await ctx.begin()
        assert ctx.state == TransactionState.ACTIVE
        
        # コミット
        await ctx.commit()
        assert ctx.state == TransactionState.COMMITTED
        
        # コミット済みのトランザクションに対する操作はエラー
        with pytest.raises(TransactionError):
            await ctx.rollback()

    @pytest.mark.asyncio
    async def test_transaction_logging(self, transaction_manager):
        """トランザクションログ記録のテスト"""
        transaction_manager.enable_logging = True
        
        async with transaction_manager.transaction() as ctx:
            await ctx.neo4j_execute("MATCH (n) RETURN n")
            await ctx.postgres_execute("SELECT * FROM users")
        
        # ログが記録されたことを確認
        logs = await transaction_manager.get_transaction_logs(ctx.transaction_id)
        assert len(logs) > 0
        assert any(log["action"] == "begin" for log in logs)
        assert any(log["action"] == "commit" for log in logs)