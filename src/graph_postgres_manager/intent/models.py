"""Intent-related data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class IntentMapping:
    """Represents a mapping between an intent and AST nodes."""
    
    id: Optional[UUID] = None
    intent_id: str = ""
    ast_node_id: str = ""
    source_id: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class IntentVector:
    """Represents an intent with its vector embedding."""
    
    intent_id: str
    vector: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate vector dimensions."""
        if len(self.vector) != 768:
            raise ValueError(f"Vector must have 768 dimensions, got {len(self.vector)}")