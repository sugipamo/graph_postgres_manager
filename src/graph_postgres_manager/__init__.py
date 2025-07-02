"""Neo4jとPostgreSQLの統合管理を行うライブラリ"""

from .config import ConnectionConfig
from .exceptions import (
    ConfigurationError,
    ConnectionException,
    DataOperationError,
    GraphPostgresManagerException,
    HealthCheckError,
    Neo4jConnectionError,
    PoolExhaustedError,
    PostgresConnectionError,
    RetryExhaustedError,
    TimeoutError,
    ValidationError,
)
from .intent import IntentManager, IntentMapping, IntentVector
from .manager import GraphPostgresManager
from .models import ConnectionState, HealthStatus

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
    "PoolExhaustedError",
    "PostgresConnectionError",
    "RetryExhaustedError",
    "TimeoutError",
    "ValidationError",
]
