"""Custom exceptions for graph_postgres_manager."""

from typing import Optional


class GraphPostgresManagerException(Exception):
    """Base exception for all graph_postgres_manager exceptions."""
    pass


class ConnectionException(GraphPostgresManagerException):
    """Raised when connection-related errors occur."""
    pass


class Neo4jConnectionError(ConnectionException):
    """Raised when Neo4j connection fails."""
    pass


class PostgresConnectionError(ConnectionException):
    """Raised when PostgreSQL connection fails."""
    pass


class ConfigurationError(GraphPostgresManagerException):
    """Raised when configuration is invalid."""
    pass


class PoolExhaustedError(ConnectionException):
    """Raised when connection pool is exhausted."""
    pass


class HealthCheckError(GraphPostgresManagerException):
    """Raised when health check fails."""
    pass


class TimeoutError(GraphPostgresManagerException):
    """Raised when operation times out."""
    pass


class RetryExhaustedError(GraphPostgresManagerException):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, last_error: Optional[Exception] = None):
        super().__init__(message)
        self.last_error = last_error