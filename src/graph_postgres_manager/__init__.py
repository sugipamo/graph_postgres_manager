"""Neo4jとPostgreSQLの統合管理を行うライブラリ"""

from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.exceptions import (
    ConfigurationError,
    ConnectionException,
    DataOperationError,
    GraphPostgresManagerException,
    HealthCheckError,
    Neo4jConnectionError,
    OperationTimeoutError,
    PoolExhaustedError,
    PostgresConnectionError,
    RetryExhaustedError,
    ValidationError,
)
from graph_postgres_manager.intent import IntentManager, IntentMapping, IntentVector
from graph_postgres_manager.manager import GraphPostgresManager
from graph_postgres_manager.models import ConnectionState, HealthStatus
from graph_postgres_manager.search import (
    SearchFilter,
    SearchManager,
    SearchQuery,
    SearchResult,
    SearchType,
)

__version__ = "0.1.0"

__all__ = [
    "ConfigurationError",
    "ConnectionConfig",
    "ConnectionException",
    "ConnectionState",
    "DataOperationError",
    "GraphPostgresManager",
    "GraphPostgresManagerException",
    "HealthCheckError",
    "HealthStatus",
    "IntentManager",
    "IntentMapping",
    "IntentVector",
    "Neo4jConnectionError",
    "OperationTimeoutError",
    "PoolExhaustedError",
    "PostgresConnectionError",
    "RetryExhaustedError",
    "SearchFilter",
    "SearchManager",
    "SearchQuery",
    "SearchResult",
    "SearchType",
    "ValidationError",
]
