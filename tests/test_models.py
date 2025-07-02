"""Tests for data models."""

from datetime import datetime

from graph_postgres_manager import ConnectionState, HealthStatus


class TestConnectionState:
    """Tests for ConnectionState enum."""
    
    def test_connection_states(self):
        """Test all connection states."""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.RECONNECTING.value == "reconnecting"
        assert ConnectionState.FAILED.value == "failed"
        assert ConnectionState.CLOSED.value == "closed"
    
    def test_state_comparison(self):
        """Test state comparison."""
        assert ConnectionState.CONNECTED != ConnectionState.DISCONNECTED
        assert ConnectionState.CONNECTED == ConnectionState.CONNECTED


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""
    
    def test_health_status_creation(self):
        """Test creating health status."""
        status = HealthStatus(
            neo4j_connected=True,
            postgres_connected=True,
            neo4j_latency_ms=10.5,
            postgres_latency_ms=5.2,
        )
        
        assert status.neo4j_connected is True
        assert status.postgres_connected is True
        assert status.neo4j_latency_ms == 10.5
        assert status.postgres_latency_ms == 5.2
        assert isinstance(status.timestamp, datetime)
        assert status.neo4j_error is None
        assert status.postgres_error is None
    
    def test_health_status_with_errors(self):
        """Test health status with errors."""
        status = HealthStatus(
            neo4j_connected=False,
            postgres_connected=True,
            neo4j_latency_ms=0.0,
            postgres_latency_ms=8.3,
            neo4j_error="Connection refused",
            postgres_error=None,
        )
        
        assert status.neo4j_connected is False
        assert status.postgres_connected is True
        assert status.neo4j_error == "Connection refused"
        assert status.postgres_error is None
    
    def test_is_healthy_property(self):
        """Test is_healthy property."""
        # Both healthy
        status = HealthStatus(
            neo4j_connected=True,
            postgres_connected=True,
            neo4j_latency_ms=10.0,
            postgres_latency_ms=5.0,
        )
        assert status.is_healthy is True
        
        # Neo4j unhealthy
        status = HealthStatus(
            neo4j_connected=False,
            postgres_connected=True,
            neo4j_latency_ms=0.0,
            postgres_latency_ms=5.0,
        )
        assert status.is_healthy is False
        
        # PostgreSQL unhealthy
        status = HealthStatus(
            neo4j_connected=True,
            postgres_connected=False,
            neo4j_latency_ms=10.0,
            postgres_latency_ms=0.0,
        )
        assert status.is_healthy is False
        
        # Both unhealthy
        status = HealthStatus(
            neo4j_connected=False,
            postgres_connected=False,
            neo4j_latency_ms=0.0,
            postgres_latency_ms=0.0,
        )
        assert status.is_healthy is False
    
    def test_total_latency_property(self):
        """Test total_latency_ms property."""
        status = HealthStatus(
            neo4j_connected=True,
            postgres_connected=True,
            neo4j_latency_ms=10.5,
            postgres_latency_ms=5.3,
        )
        
        assert status.total_latency_ms == 15.8
    
    def test_custom_timestamp(self):
        """Test custom timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        status = HealthStatus(
            neo4j_connected=True,
            postgres_connected=True,
            neo4j_latency_ms=10.0,
            postgres_latency_ms=5.0,
            timestamp=custom_time,
        )
        
        assert status.timestamp == custom_time