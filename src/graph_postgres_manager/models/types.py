"""Type definitions for graph_postgres_manager."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass
class HealthStatus:
    """Health status of database connections."""
    neo4j_connected: bool
    postgres_connected: bool
    neo4j_latency_ms: float
    postgres_latency_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    neo4j_error: str | None = None
    postgres_error: str | None = None
    
    @property
    def is_healthy(self) -> bool:
        """Check if all connections are healthy."""
        return self.neo4j_connected and self.postgres_connected
    
    @property
    def total_latency_ms(self) -> float:
        """Calculate total latency."""
        return self.neo4j_latency_ms + self.postgres_latency_ms