"""Custom exceptions for graph_postgres_manager."""



class GraphPostgresManagerError(Exception):
    """Base exception for all graph_postgres_manager exceptions."""


class ConnectionError(GraphPostgresManagerError):
    """Raised when connection-related errors occur."""


class Neo4jConnectionError(ConnectionError):
    """Raised when Neo4j connection fails."""


class PostgresConnectionError(ConnectionError):
    """Raised when PostgreSQL connection fails."""


class ConfigurationError(GraphPostgresManagerError):
    """Raised when configuration is invalid."""


class PoolExhaustedError(ConnectionError):
    """Raised when connection pool is exhausted."""


class HealthCheckError(GraphPostgresManagerError):
    """Raised when health check fails."""


class OperationTimeoutError(GraphPostgresManagerError):
    """Raised when operation times out."""


class RetryExhaustedError(GraphPostgresManagerError):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, last_error: Exception | None = None):
        super().__init__(message)
        self.last_error = last_error


class SchemaError(GraphPostgresManagerError):
    """Raised when schema-related operations fail."""


class MetadataError(GraphPostgresManagerError):
    """Raised when metadata operations fail."""


class ValidationError(GraphPostgresManagerError):
    """Raised when data validation fails."""


class DataOperationError(GraphPostgresManagerError):
    """Raised when data operations fail."""
