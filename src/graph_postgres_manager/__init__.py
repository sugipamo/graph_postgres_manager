"""Neo4jとPostgreSQLの統合管理を行うライブラリ"""

from graph_postgres_manager.config import ConnectionConfig
from graph_postgres_manager.exceptions import (
    ConfigurationError,
    ConnectionError,
    DataOperationError,
    GraphPostgresManagerError,
    HealthCheckError,
    Neo4jConnectionError,
    OperationTimeoutError,
    PoolExhaustedError,
    PostgresConnectionError,
    RetryExhaustedError,
    ValidationError,
)
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
    "ConnectionError",
    "ConnectionState",
    "DataOperationError",
    "GraphPostgresManager",
    "GraphPostgresManagerError",
    "HealthCheckError",
    "HealthStatus",
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
