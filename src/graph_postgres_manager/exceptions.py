"""Custom exceptions for graph_postgres_manager."""



class GraphPostgresManagerException(Exception):
    """Base exception for all graph_postgres_manager exceptions."""


class ConnectionException(GraphPostgresManagerException):
    """Raised when connection-related errors occur."""


class Neo4jConnectionError(ConnectionException):
    """Raised when Neo4j connection fails."""


class PostgresConnectionError(ConnectionException):
    """Raised when PostgreSQL connection fails."""


class ConfigurationError(GraphPostgresManagerException):
    """Raised when configuration is invalid."""


class PoolExhaustedError(ConnectionException):
    """Raised when connection pool is exhausted."""


class HealthCheckError(GraphPostgresManagerException):
    """Raised when health check fails."""


class OperationTimeoutError(GraphPostgresManagerException):
    """Raised when operation times out."""


class RetryExhaustedError(GraphPostgresManagerException):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, last_error: Exception | None = None):
        super().__init__(message)
        self.last_error = last_error


class SchemaError(GraphPostgresManagerException):
    """Raised when schema-related operations fail."""


class MetadataError(GraphPostgresManagerException):
    """Raised when metadata operations fail."""


class ValidationError(GraphPostgresManagerException):
    """Raised when data validation fails."""


class DataOperationError(GraphPostgresManagerException):
    """Raised when data operations fail."""
