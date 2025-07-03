"""Mock transaction management implementation.

This module provides mock transaction management that simulates
distributed transactions across Neo4j and PostgreSQL.
"""

from typing import Dict, Any, Optional, List
import uuid
import time
import asyncio
from contextlib import asynccontextmanager

from .data_store import InMemoryDataStore


class MockTransactionContext:
    """Mock transaction context for managing distributed transactions."""
    
    def __init__(
        self,
        tx_id: str,
        data_store: InMemoryDataStore,
        neo4j_conn: Any,
        postgres_conn: Any,
        timeout: Optional[float] = None
    ):
        """Initialize transaction context.
        
        Args:
            tx_id: Transaction ID
            data_store: Shared data store
            neo4j_conn: Mock Neo4j connection
            postgres_conn: Mock PostgreSQL connection
            timeout: Transaction timeout in seconds
        """
        self.tx_id = tx_id
        self.data_store = data_store
        self.neo4j = neo4j_conn
        self.postgres = postgres_conn
        self.timeout = timeout
        self.start_time = time.time()
        self._committed = False
        self._rolled_back = False
    
    async def commit(self) -> None:
        """Commit the transaction."""
        if self._committed or self._rolled_back:
            raise RuntimeError("Transaction already finished")
        
        # Check timeout
        if self.timeout and (time.time() - self.start_time) > self.timeout:
            raise TimeoutError("Transaction timeout exceeded")
        
        # Simulate commit delay
        await asyncio.sleep(0.001)
        
        self.data_store.commit_transaction(self.tx_id)
        self._committed = True
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._committed or self._rolled_back:
            raise RuntimeError("Transaction already finished")
        
        # Simulate rollback delay
        await asyncio.sleep(0.001)
        
        self.data_store.rollback_transaction(self.tx_id)
        self._rolled_back = True


class MockTransactionManager:
    """Mock implementation of transaction manager."""
    
    def __init__(
        self,
        data_store: InMemoryDataStore,
        neo4j_connection: Any,
        postgres_connection: Any,
        enable_two_phase_commit: bool = False,
        enable_logging: bool = False
    ):
        """Initialize mock transaction manager.
        
        Args:
            data_store: Shared data store
            neo4j_connection: Mock Neo4j connection
            postgres_connection: Mock PostgreSQL connection
            enable_two_phase_commit: Enable 2PC simulation
            enable_logging: Enable transaction logging
        """
        self.data_store = data_store
        self.neo4j_connection = neo4j_connection
        self.postgres_connection = postgres_connection
        self.enable_two_phase_commit = enable_two_phase_commit
        self.enable_logging = enable_logging
        self._active_transactions: Dict[str, MockTransactionContext] = {}
    
    @asynccontextmanager
    async def begin_transaction(self, timeout: Optional[float] = None):
        """Begin a new transaction.
        
        Args:
            timeout: Transaction timeout in seconds
            
        Yields:
            Transaction context
        """
        tx_id = str(uuid.uuid4())
        
        # Initialize transaction in data store
        self.data_store.begin_transaction(tx_id)
        
        # Create transaction context
        tx_context = MockTransactionContext(
            tx_id=tx_id,
            data_store=self.data_store,
            neo4j_conn=self.neo4j_connection,
            postgres_conn=self.postgres_connection,
            timeout=timeout
        )
        
        self._active_transactions[tx_id] = tx_context
        
        try:
            yield tx_context
            
            # Auto-commit if not explicitly handled
            if not tx_context._committed and not tx_context._rolled_back:
                await tx_context.commit()
                
        except Exception as e:
            # Auto-rollback on exception
            if not tx_context._committed and not tx_context._rolled_back:
                await tx_context.rollback()
            raise
        finally:
            # Clean up
            if tx_id in self._active_transactions:
                del self._active_transactions[tx_id]
    
    def get_active_transactions(self) -> List[str]:
        """Get list of active transaction IDs."""
        return list(self._active_transactions.keys())
    
    async def rollback_all(self) -> None:
        """Rollback all active transactions."""
        for tx_id, tx_context in list(self._active_transactions.items()):
            if not tx_context._committed and not tx_context._rolled_back:
                await tx_context.rollback()