"""Neo4jとPostgreSQLの統合管理を行うライブラリ"""

from .config import ConnectionConfig
from .exceptions import (
    ConfigurationError,
    ConnectionException,
    GraphPostgresManagerException,
    HealthCheckError,
    Neo4jConnectionError,
    PoolExhaustedError,
    PostgresConnectionError,
    RetryExhaustedError,
    TimeoutError,
)
from .manager import GraphPostgresManager
from .models import ConnectionState, HealthStatus

__version__ = "0.1.0"

__all__ = [
    "ConfigurationError",
    "ConnectionConfig",
    "ConnectionException",
    "ConnectionState",
    "GraphPostgresManager",
    "GraphPostgresManagerException",
    "HealthCheckError",
    "HealthStatus",
    "Neo4jConnectionError",
    "PoolExhaustedError",
    "PostgresConnectionError",
    "RetryExhaustedError",
    "TimeoutError",
]
