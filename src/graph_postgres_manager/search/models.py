"""Models for search functionality."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SearchType(Enum):
    """Types of search supported."""
    GRAPH = "graph"
    VECTOR = "vector"
    TEXT = "text"
    UNIFIED = "unified"


@dataclass
class SearchFilter:
    """Filter criteria for search operations."""
    node_types: list[str] | None = None
    source_ids: list[str] | None = None
    file_patterns: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float = 0.0
    max_results: int = 100
    metadata_filters: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate filter values."""
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")
        if self.max_results < 1:
            raise ValueError("max_results must be at least 1")


@dataclass
class SearchQuery:
    """Search query parameters."""
    query: str
    search_types: list[SearchType] = field(default_factory=lambda: [SearchType.UNIFIED])
    filters: SearchFilter = field(default_factory=SearchFilter)
    vector: list[float] | None = None
    weights: dict[SearchType, float] = field(default_factory=lambda: {
        SearchType.GRAPH: 0.4,
        SearchType.VECTOR: 0.4,
        SearchType.TEXT: 0.2
    })
    
    def __post_init__(self):
        """Validate query parameters."""
        if not self.query and not self.vector:
            raise ValueError("Either query text or vector must be provided")
        
        if self.vector and len(self.vector) != 768:
            raise ValueError("Vector must have exactly 768 dimensions")
        
        # Normalize weights
        if self.weights:
            total = sum(self.weights.values())
            if total > 0:
                self.weights = {k: v/total for k, v in self.weights.items()}


@dataclass
class SearchResult:
    """Individual search result."""
    id: str
    source_id: str
    node_type: str | None = None
    content: str | None = None
    score: float = 0.0
    search_type: SearchType = SearchType.UNIFIED
    metadata: dict[str, Any] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    file_path: str | None = None
    line_number: int | None = None
    
    def __post_init__(self):
        """Validate result values."""
        if not 0.0 <= self.score <= 1.0:
            self.score = max(0.0, min(1.0, self.score))