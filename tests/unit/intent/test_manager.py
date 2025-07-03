"""Unit tests for IntentManager."""

import json
from unittest.mock import AsyncMock, MagicMock, call
import pytest

from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import (
    ValidationError,
    DataOperationError,
)
from graph_postgres_manager.intent.manager import IntentManager


@pytest.fixture
def mock_postgres():
    """Create a mock PostgreSQL connection."""
    mock = MagicMock(spec=PostgresConnection)
    mock.execute = AsyncMock()
    return mock


@pytest.fixture
def intent_manager(mock_postgres):
    """Create an IntentManager instance with mock connection."""
    return IntentManager(mock_postgres)


class TestIntentManager:
    """Test cases for IntentManager."""
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_basic(self, intent_manager, mock_postgres):
        """Test basic intent-AST linking."""
        # Mock successful insert
        mock_postgres.execute.side_effect = [
            None,  # BEGIN
            [{"id": "mapping_id_1"}],  # First INSERT
            [{"id": "mapping_id_2"}],  # Second INSERT
            None,  # COMMIT
        ]
        
        result = await intent_manager.link_intent_to_ast(
            intent_id="intent_123",
            ast_node_ids=["ast_1", "ast_2"],
            source_id="src_456",
            confidence=0.9,
            metadata={"key": "value"}
        )
        
        assert result == {
            "intent_id": "intent_123",
            "mapped_ast_nodes": 2,
            "mapping_ids": ["mapping_id_1", "mapping_id_2"],
            "vector_stored": False
        }
        
        # Verify transaction calls
        assert mock_postgres.execute.call_count == 4
        assert mock_postgres.execute.call_args_list[0] == call("BEGIN")
        assert mock_postgres.execute.call_args_list[3] == call("COMMIT")
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_with_vector(self, intent_manager, mock_postgres):
        """Test intent-AST linking with vector storage."""
        vector = [0.1] * 768
        
        # Mock successful operations
        mock_postgres.execute.side_effect = [
            None,  # BEGIN
            [{"id": "mapping_id_1"}],  # INSERT mapping
            None,  # INSERT vector
            None,  # COMMIT
        ]
        
        result = await intent_manager.link_intent_to_ast(
            intent_id="intent_123",
            ast_node_ids=["ast_1"],
            source_id="src_456",
            intent_vector=vector
        )
        
        assert result["vector_stored"] is True
        
        # Verify vector insert call
        vector_call = mock_postgres.execute.call_args_list[2]
        assert "intent_vectors" in vector_call[0][0]
        assert vector_call[0][1][0] == "intent_123"
        assert vector_call[0][1][1] == vector
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_validation(self, intent_manager):
        """Test parameter validation."""
        # Missing required parameters
        with pytest.raises(ValidationError):
            await intent_manager.link_intent_to_ast(
                intent_id="",
                ast_node_ids=["ast_1"],
                source_id="src_456"
            )
        
        # Invalid confidence
        with pytest.raises(ValidationError):
            await intent_manager.link_intent_to_ast(
                intent_id="intent_123",
                ast_node_ids=["ast_1"],
                source_id="src_456",
                confidence=1.5
            )
        
        # Invalid vector dimensions
        with pytest.raises(ValidationError):
            await intent_manager.link_intent_to_ast(
                intent_id="intent_123",
                ast_node_ids=["ast_1"],
                source_id="src_456",
                intent_vector=[0.1] * 512  # Wrong size
            )
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_rollback(self, intent_manager, mock_postgres):
        """Test transaction rollback on error."""
        # Mock error during insert
        mock_postgres.execute.side_effect = [
            None,  # BEGIN
            Exception("Database error"),  # INSERT fails
            None,  # ROLLBACK
        ]
        
        with pytest.raises(DataOperationError):
            await intent_manager.link_intent_to_ast(
                intent_id="intent_123",
                ast_node_ids=["ast_1"],
                source_id="src_456"
            )
        
        # Verify rollback was called
        assert mock_postgres.execute.call_args_list[-1] == call("ROLLBACK")
    
    @pytest.mark.asyncio
    async def test_get_ast_nodes_by_intent(self, intent_manager, mock_postgres):
        """Test retrieving AST nodes by intent."""
        # Mock query result
        mock_postgres.execute.return_value = [
            {
                "ast_node_id": "ast_1",
                "source_id": "src_1",
                "confidence": 0.9,
                "metadata": {"key": "value"},
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 2)
            },
            {
                "ast_node_id": "ast_2",
                "source_id": "src_2",
                "confidence": 0.8,
                "metadata": None,
                "created_at": datetime(2024, 1, 1),
                "updated_at": None
            },
        ]
        
        result = await intent_manager.get_ast_nodes_by_intent("intent_123", min_confidence=0.7)
        
        assert len(result) == 2
        assert result[0]["ast_node_id"] == "ast_1"
        assert result[0]["confidence"] == 0.9
        assert result[0]["metadata"] == {"key": "value"}
        assert result[1]["metadata"] == {}
        
        # Verify query parameters
        call_args = mock_postgres.execute.call_args
        assert call_args[0][1] == ("intent_123", 0.7)
    
    @pytest.mark.asyncio
    async def test_search_ast_by_intent_vector(self, intent_manager, mock_postgres):
        """Test vector similarity search."""
        vector = [0.1] * 768
        stored_vector = [0.1] * 768  # Same vector for high similarity
        
        # Mock vector fetch results
        mock_postgres.execute.side_effect = [
            # First call: get all intent vectors
            [
                {"intent_id": "intent_1", "vector": stored_vector},
                {"intent_id": "intent_2", "vector": [0.2] * 768},
            ],
            # Second call: get mappings for intent_1
            [
                {
                    "ast_node_id": "ast_1",
                    "source_id": "src_1",
                    "confidence": 0.9,
                    "metadata": {"key": "value"}
                },
            ],
            # Third call: get mappings for intent_2 (if similarity is high enough)
            [
                {
                    "ast_node_id": "ast_2",
                    "source_id": "src_2",
                    "confidence": 0.8,
                    "metadata": None
                },
            ],
        ]
        
        result = await intent_manager.search_ast_by_intent_vector(
            intent_vector=vector,
            limit=10,
            threshold=0.7
        )
        
        assert len(result) >= 1  # At least one result
        assert result[0]["ast_node_id"] == "ast_1"
        assert result[0]["similarity"] >= 0.9  # High similarity expected
        
        # Verify vector query was called
        first_call = mock_postgres.execute.call_args_list[0]
        assert "intent_vectors" in first_call[0][0]
    
    @pytest.mark.asyncio
    async def test_update_intent_confidence(self, intent_manager, mock_postgres):
        """Test updating confidence score."""
        mock_postgres.execute.return_value = []  # UPDATE returns empty list
        
        result = await intent_manager.update_intent_confidence(
            intent_id="intent_123",
            ast_node_id="ast_456",
            new_confidence=0.75
        )
        
        assert result is True
        
        # Verify update query
        call_args = mock_postgres.execute.call_args
        assert "UPDATE intent_ast_map" in call_args[0][0]
        assert call_args[0][1] == (0.75, "intent_123", "ast_456")
    
    @pytest.mark.asyncio
    async def test_remove_intent_mapping(self, intent_manager, mock_postgres):
        """Test removing intent mappings."""
        # Test removing specific mapping
        mock_postgres.execute.return_value = [{"1": 1}]  # RETURNING 1
        
        count = await intent_manager.remove_intent_mapping(
            intent_id="intent_123",
            ast_node_id="ast_456"
        )
        
        assert count == 1
        
        # Verify specific delete
        call_args = mock_postgres.execute.call_args
        assert "ast_node_id = %s" in call_args[0][0]
        assert call_args[0][1] == ("intent_123", "ast_456")
        
        # Test removing all mappings for an intent
        mock_postgres.execute.reset_mock()
        mock_postgres.execute.return_value = [{"1": 1}, {"1": 1}]  # RETURNING 1 for each deleted row
        
        count = await intent_manager.remove_intent_mapping("intent_123")
        
        assert count == 2
        
        # Verify delete all
        call_args = mock_postgres.execute.call_args
        assert "ast_node_id = %s" not in call_args[0][0]
        assert call_args[0][1] == ("intent_123",)
    
    @pytest.mark.asyncio
    async def test_batch_link_intents(self, intent_manager, mock_postgres):
        """Test batch linking of intents."""
        mappings = [
            ("intent_1", ["ast_1", "ast_2"], "src_1", 0.9, {"batch": 1}),
            ("intent_2", ["ast_3"], "src_2", 0.8, None),
        ]
        
        # Mock successful inserts
        mock_postgres.execute.side_effect = [
            None,  # BEGIN
            None,  # Insert 1-1
            None,  # Insert 1-2
            None,  # Insert 2-1
            None,  # COMMIT
        ]
        
        result = await intent_manager.batch_link_intents(mappings)
        
        assert result["total_mappings"] == 3
        assert result["failed_mappings"] == 0
        assert result["success_rate"] == 1.0
        
        # Verify transaction
        assert mock_postgres.execute.call_args_list[0] == call("BEGIN")
        assert mock_postgres.execute.call_args_list[-1] == call("COMMIT")


# Import datetime for test
from datetime import datetime