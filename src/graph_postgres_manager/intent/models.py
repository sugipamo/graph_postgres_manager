"""Models for intent management."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class IntentMapping:
    """Represents a mapping between an intent and AST nodes."""
    
    id: str | None = None
    intent_id: str = ""
    ast_node_id: str = ""
    source_id: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class IntentVector:
    """Represents an intent with its vector embedding."""
    
    intent_id: str
    vector: list[float]
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None