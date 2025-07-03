"""トランザクション管理の実装"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from graph_postgres_manager.connections.neo4j import Neo4jConnection
from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import GraphPostgresManagerException

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """トランザクションの状態"""
    PENDING = "pending"
    ACTIVE = "active"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class TransactionError(GraphPostgresManagerException):
    """トランザクション関連のエラー"""


class TransactionRollbackError(TransactionError):
    """ロールバック時のエラー"""


class TransactionContext:
    """トランザクションコンテキスト"""
    
    def __init__(
        self,
        manager: "TransactionManager",
        transaction_id: str,
        is_nested: bool = False,
        timeout: float | None = None
    ):
        self.manager = manager
        self.transaction_id = transaction_id
        self.is_nested = is_nested
        self.timeout = timeout
        self.state = TransactionState.PENDING
        self._neo4j_tx = None
        self._postgres_tx = None
        self._start_time = None
        self._end_time = None
        self._operations: list[dict[str, Any]] = []
    
    async def begin(self) -> None:
        """トランザクションを開始"""
        if self.state != TransactionState.PENDING:
            raise TransactionError(f"Cannot begin transaction in state {self.state}")
        
        self._start_time = datetime.now(UTC)
        self.state = TransactionState.ACTIVE
        
        if not self.is_nested:
            self._neo4j_tx = await self.manager.neo4j_connection.begin_transaction()
            self._postgres_tx = await self.manager.postgres_connection.begin_transaction()
        
        await self._log_operation("begin", {"nested": self.is_nested})
    
    async def commit(self) -> None:
        """トランザクションをコミット"""
        if self.state != TransactionState.ACTIVE:
            raise TransactionError(f"Cannot commit transaction in state {self.state}")
        
        try:
            if self.manager.enable_two_phase_commit and not self.is_nested:
                await self._two_phase_commit()
            else:
                await self._single_phase_commit()
            
            self.state = TransactionState.COMMITTED
            self._end_time = datetime.now(UTC)
            await self._log_operation("commit", {"duration": self._get_duration()})
            
        except Exception as e:
            self.state = TransactionState.FAILED
            await self._log_operation("commit_failed", {"error": str(e)})
            raise TransactionError(f"Failed to commit transaction: {e}") from e
    
    async def rollback(self) -> None:
        """トランザクションをロールバック"""
        if self.state not in (
            TransactionState.ACTIVE, TransactionState.PREPARING, TransactionState.PREPARED
        ):
            raise TransactionError(f"Cannot rollback transaction in state {self.state}")
        
        self.state = TransactionState.ROLLING_BACK
        errors = []
        
        try:
            if not self.is_nested:
                if self._neo4j_tx:
                    try:
                        await self.manager.neo4j_connection.rollback_transaction(self._neo4j_tx)
                    except Exception as e:
                        errors.append(f"Neo4j rollback error: {e}")
                
                if self._postgres_tx:
                    try:
                        await self.manager.postgres_connection.rollback_transaction(
                            self._postgres_tx
                        )
                    except Exception as e:
                        errors.append(f"PostgreSQL rollback error: {e}")
            
            if errors:
                raise TransactionRollbackError(f"Rollback errors: {', '.join(errors)}")
            
            self.state = TransactionState.ROLLED_BACK
            self._end_time = datetime.now(UTC)
            await self._log_operation("rollback", {"duration": self._get_duration()})
            
        except Exception as e:
            self.state = TransactionState.FAILED
            await self._log_operation("rollback_failed", {"error": str(e)})
            raise
    
    async def neo4j_execute(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Neo4jでクエリを実行"""
        if self.state != TransactionState.ACTIVE:
            raise TransactionError(f"Cannot execute query in transaction state {self.state}")
        
        await self._log_operation("neo4j_execute", {"query": query, "parameters": parameters})
        return await self.manager.neo4j_connection.execute_query(
            query, parameters, transaction=self._neo4j_tx
        )
    
    async def postgres_execute(
        self, query: str, parameters: list | dict | None = None
    ) -> list[dict[str, Any]]:
        """PostgreSQLでクエリを実行"""
        if self.state != TransactionState.ACTIVE:
            raise TransactionError(f"Cannot execute query in transaction state {self.state}")
        
        await self._log_operation("postgres_execute", {"query": query, "parameters": parameters})
        return await self.manager.postgres_connection.execute(
            query, parameters, transaction=self._postgres_tx
        )
    
    async def _single_phase_commit(self) -> None:
        """単一フェーズコミット"""
        if not self.is_nested:
            self.state = TransactionState.COMMITTING
            await self.manager.neo4j_connection.commit_transaction(self._neo4j_tx)
            await self.manager.postgres_connection.commit_transaction(self._postgres_tx)
    
    async def _two_phase_commit(self) -> None:
        """2フェーズコミットプロトコル"""
        # Prepare phase
        self.state = TransactionState.PREPARING
        prepare_errors = []
        
        try:
            await self.manager.neo4j_connection.prepare_transaction(self._neo4j_tx)
        except Exception as e:
            prepare_errors.append(f"Neo4j prepare error: {e}")
        
        try:
            await self.manager.postgres_connection.prepare_transaction(self._postgres_tx)
        except Exception as e:
            prepare_errors.append(f"PostgreSQL prepare error: {e}")
        
        if prepare_errors:
            await self.rollback()
            raise TransactionError(f"Prepare phase failed: {', '.join(prepare_errors)}")
        
        self.state = TransactionState.PREPARED
        
        # Commit phase
        self.state = TransactionState.COMMITTING
        commit_errors = []
        
        try:
            await self.manager.neo4j_connection.commit_prepared(self._neo4j_tx)
        except Exception as e:
            commit_errors.append(f"Neo4j commit error: {e}")
        
        try:
            await self.manager.postgres_connection.commit_prepared(self._postgres_tx)
        except Exception as e:
            commit_errors.append(f"PostgreSQL commit error: {e}")
        
        if commit_errors:
            # 部分的なコミットが発生した可能性があるため、状態を記録
            await self._log_operation("partial_commit", {"errors": commit_errors})
            raise TransactionError(f"Commit phase failed: {', '.join(commit_errors)}")
    
    async def _log_operation(self, action: str, details: dict[str, Any]) -> None:
        """操作をログに記録"""
        operation = {
            "timestamp": datetime.now(UTC).isoformat(),
            "transaction_id": self.transaction_id,
            "action": action,
            "details": details
        }
        self._operations.append(operation)
        
        if self.manager.enable_logging:
            await self.manager._save_transaction_log(operation)
    
    def _get_duration(self) -> float:
        """トランザクションの実行時間を取得"""
        if self._start_time and self._end_time:
            return (self._end_time - self._start_time).total_seconds()
        return 0.0


class TransactionManager:
    """トランザクションマネージャー"""
    
    def __init__(
        self,
        neo4j_connection: Neo4jConnection,
        postgres_connection: PostgresConnection,
        enable_two_phase_commit: bool = False,
        enable_logging: bool = False,
        default_timeout: float | None = None
    ):
        self.neo4j_connection = neo4j_connection
        self.postgres_connection = postgres_connection
        self.enable_two_phase_commit = enable_two_phase_commit
        self.enable_logging = enable_logging
        self.default_timeout = default_timeout
        self._active_transactions: dict[str, TransactionContext] = {}
        self._transaction_logs: list[dict[str, Any]] = []
    
    @asynccontextmanager
    async def transaction(self, timeout: float | None = None) -> TransactionContext:
        """トランザクションコンテキストマネージャー"""
        transaction_id = str(uuid.uuid4())
        is_nested = len(self._active_transactions) > 0
        
        ctx = TransactionContext(
            manager=self,
            transaction_id=transaction_id,
            is_nested=is_nested,
            timeout=timeout or self.default_timeout
        )
        
        self._active_transactions[transaction_id] = ctx
        
        try:
            await ctx.begin()
            
            if ctx.timeout:
                # タイムアウト付きでトランザクションを実行
                try:
                    async with asyncio.timeout(ctx.timeout):
                        yield ctx
                except TimeoutError:
                    await ctx.rollback()
                    raise
            else:
                yield ctx
            
            # 正常終了時、まだコミットされていなければコミット
            if ctx.state == TransactionState.ACTIVE:
                await ctx.commit()
                
        except Exception as original_error:
            # エラー発生時、まだロールバックされていなければロールバック
            if ctx.state in (
                TransactionState.ACTIVE, TransactionState.PREPARING, TransactionState.PREPARED
            ):
                try:
                    await ctx.rollback()
                except TransactionRollbackError:
                    # TransactionRollbackErrorはそのまま再発生させる
                    raise
                except Exception as rollback_error:
                    logger.error(
                        "Failed to rollback transaction %s: %s",
                        transaction_id, rollback_error
                    )
                    # ロールバックエラーをTransactionRollbackErrorとして再発生
                    raise TransactionRollbackError(
                        f"Rollback errors: {rollback_error}"
                    ) from original_error
            raise
        finally:
            del self._active_transactions[transaction_id]
    
    async def get_transaction_logs(self, transaction_id: str | None = None) -> list[dict[str, Any]]:
        """トランザクションログを取得"""
        if transaction_id:
            return [
                log for log in self._transaction_logs 
                if log["transaction_id"] == transaction_id
            ]
        return self._transaction_logs.copy()
    
    async def _save_transaction_log(self, log_entry: dict[str, Any]) -> None:
        """トランザクションログを保存"""
        self._transaction_logs.append(log_entry)
        
        # PostgreSQLにログを永続化する場合
        if self.enable_logging and hasattr(self.postgres_connection, "execute"):
            try:
                await self.postgres_connection.execute(
                    """
                    INSERT INTO transaction_logs (transaction_id, timestamp, action, details)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        log_entry["transaction_id"],
                        log_entry["timestamp"],
                        log_entry["action"],
                        log_entry["details"]
                    ]
                )
            except Exception as e:
                logger.error("Failed to save transaction log: %s", e)