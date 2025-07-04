"""Tests for custom exceptions."""

import pytest

from graph_postgres_manager import (
    ConfigurationError,
    ConnectionException,
    GraphPostgresManagerError,
    HealthCheckError,
    Neo4jConnectionError,
    OperationTimeoutError,
    PoolExhaustedError,
    PostgresConnectionError,
    RetryExhaustedError,
)


class TestExceptions:
    """Tests for exception hierarchy and behavior."""
    
    def test_base_exception(self):
        """Test base exception."""
        exc = GraphPostgresManagerError("Base error")
        assert str(exc) == "Base error"
        assert isinstance(exc, Exception)
    
    def test_connection_exceptions(self):
        """Test connection-related exceptions."""
        # Base connection exception
        exc = ConnectionException("Connection failed")
        assert isinstance(exc, GraphPostgresManagerError)
        assert str(exc) == "Connection failed"
        
        # Neo4j specific
        exc = Neo4jConnectionError("Neo4j connection failed")
        assert isinstance(exc, ConnectionException)
        assert isinstance(exc, GraphPostgresManagerError)
        
        # PostgreSQL specific
        exc = PostgresConnectionError("PostgreSQL connection failed")
        assert isinstance(exc, ConnectionException)
        assert isinstance(exc, GraphPostgresManagerError)
        
        # Pool exhausted
        exc = PoolExhaustedError("Pool exhausted")
        assert isinstance(exc, ConnectionException)
    
    def test_configuration_error(self):
        """Test configuration error."""
        exc = ConfigurationError("Invalid config")
        assert isinstance(exc, GraphPostgresManagerError)
        assert str(exc) == "Invalid config"
    
    def test_health_check_error(self):
        """Test health check error."""
        exc = HealthCheckError("Health check failed")
        assert isinstance(exc, GraphPostgresManagerError)
        assert str(exc) == "Health check failed"
    
    def test_operation_timeout_error(self):
        """Test operation timeout error."""
        exc = OperationTimeoutError("Operation timed out")
        assert isinstance(exc, GraphPostgresManagerError)
        assert str(exc) == "Operation timed out"
    
    def test_retry_exhausted_error(self):
        """Test retry exhausted error with last error."""
        last_error = ConnectionException("Last connection attempt failed")
        exc = RetryExhaustedError("All retries failed", last_error)
        
        assert isinstance(exc, GraphPostgresManagerError)
        assert str(exc) == "All retries failed"
        assert exc.last_error == last_error
        assert isinstance(exc.last_error, ConnectionException)
    
    def test_retry_exhausted_error_without_last_error(self):
        """Test retry exhausted error without last error."""
        exc = RetryExhaustedError("All retries failed")
        
        assert str(exc) == "All retries failed"
        assert exc.last_error is None
    
    def test_exception_inheritance_chain(self):
        """Test complete inheritance chain."""
        exc = Neo4jConnectionError("Neo4j error")
        
        # Check full inheritance chain
        assert isinstance(exc, Neo4jConnectionError)
        assert isinstance(exc, ConnectionException)
        assert isinstance(exc, GraphPostgresManagerError)
        assert isinstance(exc, Exception)
        
        # Ensure it can be caught at any level
        with pytest.raises(Neo4jConnectionError):
            raise exc
        
        with pytest.raises(ConnectionException):
            raise exc
        
        with pytest.raises(GraphPostgresManagerError):
            raise exc
        
        with pytest.raises(GraphPostgresManagerError):
            raise exc