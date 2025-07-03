"""Unit tests for intent models."""

import pytest
from datetime import datetime
from uuid import uuid4

from graph_postgres_manager.intent.models import IntentMapping, IntentVector


class TestIntentMapping:
    """Test cases for IntentMapping model."""
    
    def test_create_minimal(self):
        """Test creating IntentMapping with minimal fields."""
        mapping = IntentMapping()
        assert mapping.id is None
        assert mapping.intent_id == ""
        assert mapping.ast_node_id == ""
        assert mapping.source_id == ""
        assert mapping.confidence == 1.0
        assert mapping.metadata == {}
        assert mapping.created_at is None
        assert mapping.updated_at is None
    
    def test_create_full(self):
        """Test creating IntentMapping with all fields."""
        now = datetime.now()
        mapping_id = uuid4()
        
        mapping = IntentMapping(
            id=mapping_id,
            intent_id="intent_123",
            ast_node_id="ast_456",
            source_id="src_789",
            confidence=0.95,
            metadata={"key": "value"},
            created_at=now,
            updated_at=now
        )
        
        assert mapping.id == mapping_id
        assert mapping.intent_id == "intent_123"
        assert mapping.ast_node_id == "ast_456"
        assert mapping.source_id == "src_789"
        assert mapping.confidence == 0.95
        assert mapping.metadata == {"key": "value"}
        assert mapping.created_at == now
        assert mapping.updated_at == now


class TestIntentVector:
    """Test cases for IntentVector model."""
    
    def test_create_valid(self):
        """Test creating IntentVector with valid vector."""
        vector = [0.1] * 768  # 768-dimensional vector
        now = datetime.now()
        
        intent_vec = IntentVector(
            intent_id="intent_123",
            vector=vector,
            metadata={"source": "openai"},
            created_at=now
        )
        
        assert intent_vec.intent_id == "intent_123"
        assert len(intent_vec.vector) == 768
        assert intent_vec.vector[0] == 0.1
        assert intent_vec.metadata == {"source": "openai"}
        assert intent_vec.created_at == now
    
    def test_create_invalid_dimensions(self):
        """Test creating IntentVector with wrong dimensions."""
        vector = [0.1] * 512  # Wrong dimension
        
        with pytest.raises(ValueError, match="Vector must have 768 dimensions"):
            IntentVector(
                intent_id="intent_123",
                vector=vector
            )
    
    def test_create_minimal(self):
        """Test creating IntentVector with minimal fields."""
        vector = [0.0] * 768
        
        intent_vec = IntentVector(
            intent_id="intent_123",
            vector=vector
        )
        
        assert intent_vec.intent_id == "intent_123"
        assert len(intent_vec.vector) == 768
        assert intent_vec.metadata == {}
        assert intent_vec.created_at is None