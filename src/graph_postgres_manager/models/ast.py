"""AST-related models for graph_postgres_manager."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EdgeType(Enum):
    """Types of edges in the AST graph."""
    
    CHILD = "CHILD"  # Parent-child relationship
    NEXT = "NEXT"    # Sibling relationship
    DEPENDS_ON = "DEPENDS_ON"  # Dependency relationship


@dataclass
class ASTNode:
    """Represents a node in the AST graph."""
    
    id: str
    node_type: str
    source_id: str
    value: str | None = None
    lineno: int | None = None
    
    def to_cypher_properties(self) -> dict[str, Any]:
        """Convert to Cypher properties, excluding None values."""
        props = {
            "id": self.id,
            "node_type": self.node_type,
            "source_id": self.source_id,
        }
        
        if self.value is not None:
            props["value"] = self.value
        
        if self.lineno is not None:
            props["lineno"] = self.lineno
        
        return props