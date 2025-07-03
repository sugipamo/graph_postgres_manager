"""Intent-related data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class IntentMapping:
    """Represents a mapping between an intent and AST nodes."""
    
    id: UUID | None = None
    intent_id: str = ""
    ast_node_id: str = ""
    source_id: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class IntentVector:
    """Represents an intent with its vector embedding."""
    
    intent_id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    
    def __post_init__(self):
        """Validate vector dimensions."""
        if len(self.vector) != 768:
            raise ValueError(f"Vector must have 768 dimensions, got {len(self.vector)}")