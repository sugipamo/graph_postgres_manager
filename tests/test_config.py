"""Tests for connection configuration."""

import os
import pytest
from unittest.mock import patch

from graph_postgres_manager import ConnectionConfig, ConfigurationError


class TestConnectionConfig:
    """Tests for ConnectionConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ConnectionConfig()
        
        assert config.neo4j_uri == "bolt://localhost:7687"
        assert config.neo4j_auth == ("neo4j", "password")
        assert config.postgres_dsn == "postgresql://user:pass@localhost/dbname"
        assert config.connection_pool_size == 10
        assert config.max_retry_attempts == 3
        assert config.timeout_seconds == 30
        assert config.health_check_interval == 60
        assert config.enable_auto_reconnect is True
        assert config.retry_backoff_factor == 2.0
        assert config.retry_max_delay == 60
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = ConnectionConfig(
            neo4j_uri="bolt://custom:7687",
            neo4j_auth=("custom_user", "custom_pass"),
            postgres_dsn="postgresql://custom@localhost/test",
            connection_pool_size=20,
            max_retry_attempts=5,
            timeout_seconds=60,
            health_check_interval=30,
            enable_auto_reconnect=False,
            retry_backoff_factor=1.5,
            retry_max_delay=120,
        )
        
        assert config.neo4j_uri == "bolt://custom:7687"
        assert config.neo4j_auth == ("custom_user", "custom_pass")
        assert config.postgres_dsn == "postgresql://custom@localhost/test"
        assert config.connection_pool_size == 20
        assert config.max_retry_attempts == 5
        assert config.timeout_seconds == 60
        assert config.health_check_interval == 30
        assert config.enable_auto_reconnect is False
        assert config.retry_backoff_factor == 1.5
        assert config.retry_max_delay == 120
    
    @patch.dict(os.environ, {
        "NEO4J_URI": "bolt://env:7687",
        "NEO4J_USER": "env_user",
        "NEO4J_PASSWORD": "env_pass",
        "POSTGRES_DSN": "postgresql://env@localhost/envdb",
        "CONNECTION_POOL_SIZE": "15",
        "MAX_RETRY_ATTEMPTS": "4",
        "TIMEOUT_SECONDS": "45",
        "HEALTH_CHECK_INTERVAL": "90",
        "ENABLE_AUTO_RECONNECT": "false",
        "RETRY_BACKOFF_FACTOR": "3.0",
        "RETRY_MAX_DELAY": "180",
    })
    def test_env_config(self):
        """Test configuration from environment variables."""
        config = ConnectionConfig()
        
        assert config.neo4j_uri == "bolt://env:7687"
        assert config.neo4j_auth == ("env_user", "env_pass")
        assert config.postgres_dsn == "postgresql://env@localhost/envdb"
        assert config.connection_pool_size == 15
        assert config.max_retry_attempts == 4
        assert config.timeout_seconds == 45
        assert config.health_check_interval == 90
        assert config.enable_auto_reconnect is False
        assert config.retry_backoff_factor == 3.0
        assert config.retry_max_delay == 180
    
    def test_validation_errors(self):
        """Test configuration validation errors."""
        with pytest.raises(ConfigurationError, match="connection_pool_size must be at least 1"):
            ConnectionConfig(connection_pool_size=0)
        
        with pytest.raises(ConfigurationError, match="max_retry_attempts must be non-negative"):
            ConnectionConfig(max_retry_attempts=-1)
        
        with pytest.raises(ConfigurationError, match="timeout_seconds must be at least 1"):
            ConnectionConfig(timeout_seconds=0)
        
        with pytest.raises(ConfigurationError, match="health_check_interval must be at least 1"):
            ConnectionConfig(health_check_interval=0)
        
        with pytest.raises(ConfigurationError, match="retry_backoff_factor must be at least 1.0"):
            ConnectionConfig(retry_backoff_factor=0.5)
        
        with pytest.raises(ConfigurationError, match="retry_max_delay must be at least 1"):
            ConnectionConfig(retry_max_delay=0)
        
        with pytest.raises(ConfigurationError, match="neo4j_uri cannot be empty"):
            ConnectionConfig(neo4j_uri="")
        
        with pytest.raises(ConfigurationError, match="postgres_dsn cannot be empty"):
            ConnectionConfig(postgres_dsn="")
        
        with pytest.raises(ConfigurationError, match="neo4j_auth must contain valid username and password"):
            ConnectionConfig(neo4j_auth=("", "pass"))
        
        with pytest.raises(ConfigurationError, match="neo4j_auth must contain valid username and password"):
            ConnectionConfig(neo4j_auth=("user", ""))
    
    def test_mask_sensitive_data(self):
        """Test masking of sensitive configuration data."""
        config = ConnectionConfig(
            neo4j_auth=("test_user", "test_password"),
            postgres_dsn="postgresql://user:secret@localhost/db",
        )
        
        masked = config.mask_sensitive_data()
        
        assert masked["neo4j_user"] == "test_user"
        assert masked["neo4j_password"] == "****"
        assert masked["postgres_dsn"] == "postgresql://user:****@localhost/db"
        assert masked["connection_pool_size"] == 10
    
    def test_mask_dsn_variations(self):
        """Test DSN masking with various formats."""
        config = ConnectionConfig()
        
        # Standard DSN
        assert config._mask_dsn(
            "postgresql://user:pass@localhost/db"
        ) == "postgresql://user:****@localhost/db"
        
        # DSN without password
        assert config._mask_dsn(
            "postgresql://user@localhost/db"
        ) == "postgresql://user@localhost/db"
        
        # DSN without auth
        assert config._mask_dsn(
            "postgresql://localhost/db"
        ) == "postgresql://localhost/db"
        
        # Invalid DSN
        assert config._mask_dsn("invalid_dsn") == "invalid_dsn"