"""Configuration management for graph_postgres_manager."""

import os
from dataclasses import dataclass, field

from .exceptions import ConfigurationError


@dataclass
class ConnectionConfig:
    """Configuration for database connections."""
    
    # Neo4j設定
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_auth: tuple[str, str] = field(
        default_factory=lambda: (
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "password")
        )
    )
    
    # PostgreSQL設定
    postgres_dsn: str = field(
        default_factory=lambda: os.getenv(
            "POSTGRES_DSN",
            "postgresql://user:pass@localhost/dbname"
        )
    )
    
    # 共通設定
    connection_pool_size: int = field(
        default_factory=lambda: int(os.getenv("CONNECTION_POOL_SIZE", "10"))
    )
    max_retry_attempts: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    )
    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("TIMEOUT_SECONDS", "30"))
    )
    
    # ヘルスチェック設定
    health_check_interval: int = field(
        default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
    )
    enable_auto_reconnect: bool = field(
        default_factory=lambda: os.getenv("ENABLE_AUTO_RECONNECT", "true").lower() == "true"
    )
    
    # リトライ設定
    retry_backoff_factor: float = field(
        default_factory=lambda: float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))
    )
    retry_max_delay: int = field(
        default_factory=lambda: int(os.getenv("RETRY_MAX_DELAY", "60"))
    )
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate configuration values."""
        if self.connection_pool_size < 1:
            raise ConfigurationError("connection_pool_size must be at least 1")
        
        if self.max_retry_attempts < 0:
            raise ConfigurationError("max_retry_attempts must be non-negative")
        
        if self.timeout_seconds < 1:
            raise ConfigurationError("timeout_seconds must be at least 1")
        
        if self.health_check_interval < 1:
            raise ConfigurationError("health_check_interval must be at least 1")
        
        if self.retry_backoff_factor < 1.0:
            raise ConfigurationError("retry_backoff_factor must be at least 1.0")
        
        if self.retry_max_delay < 1:
            raise ConfigurationError("retry_max_delay must be at least 1")
        
        if not self.neo4j_uri:
            raise ConfigurationError("neo4j_uri cannot be empty")
        
        if not self.postgres_dsn:
            raise ConfigurationError("postgres_dsn cannot be empty")
        
        if not self.neo4j_auth[0] or not self.neo4j_auth[1]:
            raise ConfigurationError("neo4j_auth must contain valid username and password")
    
    def mask_sensitive_data(self) -> dict:
        """Return configuration with masked sensitive data."""
        return {
            "neo4j_uri": self.neo4j_uri,
            "neo4j_user": self.neo4j_auth[0],
            "neo4j_password": "****" if self.neo4j_auth[1] else "",
            "postgres_dsn": self._mask_dsn(self.postgres_dsn),
            "connection_pool_size": self.connection_pool_size,
            "max_retry_attempts": self.max_retry_attempts,
            "timeout_seconds": self.timeout_seconds,
            "health_check_interval": self.health_check_interval,
            "enable_auto_reconnect": self.enable_auto_reconnect,
            "retry_backoff_factor": self.retry_backoff_factor,
            "retry_max_delay": self.retry_max_delay,
        }
    
    @staticmethod
    def _mask_dsn(dsn: str) -> str:
        """Mask password in DSN."""
        if "://" in dsn and "@" in dsn:
            scheme_end = dsn.index("://") + 3
            at_sign = dsn.index("@")
            auth_part = dsn[scheme_end:at_sign]
            
            if ":" in auth_part:
                user_end = auth_part.index(":")
                masked_auth = auth_part[:user_end + 1] + "****"
                return dsn[:scheme_end] + masked_auth + dsn[at_sign:]
        
        return dsn