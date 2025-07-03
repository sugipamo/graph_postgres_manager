"""Unit tests for IntentManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from graph_postgres_manager.exceptions import DataOperationError, ValidationError
from graph_postgres_manager.intent.manager import IntentManager


class TestIntentManager:
    """Test cases for IntentManager."""
    
    @pytest.fixture
    def mock_postgres_connection(self):
        """Create a mock PostgreSQL connection."""
        mock = MagicMock()
        mock.get_connection = MagicMock()
        return mock
    
    @pytest.fixture
    def intent_manager(self, mock_postgres_connection):
        """Create an IntentManager instance with mocked connection."""
        return IntentManager(mock_postgres_connection)
    
    @pytest.mark.asyncio
    async def test_initialize_schema(self, intent_manager, mock_postgres_connection):
        """Test schema initialization."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchone = AsyncMock(return_value=(True,))  # pgvector available
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_conn
        mock_context.__aexit__.return_value = None
        
        mock_postgres_connection.get_connection.return_value = mock_context
        
        await intent_manager.initialize_schema()
        
        # Verify tables were created
        assert mock_conn.execute.call_count >= 4  # Tables and indexes
        assert intent_manager._schema_initialized
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_validation(self, intent_manager):
        """Test input validation for link_intent_to_ast."""
        # Test missing intent_id
        with pytest.raises(ValidationError, match="intent_id is required"):
            await intent_manager.link_intent_to_ast(
                intent_id="",
                ast_node_ids=["node1"],
                source_id="source1"
            )
        
        # Test empty ast_node_ids
        with pytest.raises(ValidationError, match="ast_node_ids cannot be empty"):
            await intent_manager.link_intent_to_ast(
                intent_id="intent1",
                ast_node_ids=[],
                source_id="source1"
            )
        
        # Test invalid confidence
        with pytest.raises(ValidationError, match="confidence must be between"):
            await intent_manager.link_intent_to_ast(
                intent_id="intent1",
                ast_node_ids=["node1"],
                source_id="source1",
                confidence=1.5
            )
        
        # Test invalid vector dimensions
        with pytest.raises(ValidationError, match="768 dimensions"):
            await intent_manager.link_intent_to_ast(
                intent_id="intent1",
                ast_node_ids=["node1"],
                source_id="source1",
                intent_vector=[1.0, 2.0, 3.0]  # Wrong size
            )
    
    @pytest.mark.asyncio
    async def test_link_intent_to_ast_success(self, intent_manager, mock_postgres_connection):
        """Test successful intent-AST linking."""
        from datetime import datetime
        intent_manager._schema_initialized = True
        
        mock_conn = AsyncMock()
        
        # Create transaction context manager
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)
        
        # Mock the mapping insert
        mock_conn.fetchone = AsyncMock(side_effect=[
            ("uuid1", datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 0, 0)),
            ("uuid2", datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 0, 0)),
            (True,),  # Vector table exists
        ])
        mock_conn.execute = AsyncMock()
        
        # Create connection context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        
        mock_postgres_connection.get_connection = MagicMock(return_value=mock_context)
        
        result = await intent_manager.link_intent_to_ast(
            intent_id="intent1",
            ast_node_ids=["node1", "node2"],
            source_id="source1",
            confidence=0.95,
            metadata={"key": "value"},
            intent_vector=[0.1] * 768
        )
        
        assert result["intent_id"] == "intent1"
        assert result["source_id"] == "source1"
        assert result["mappings_created"] == 2
        assert result["vector_stored"] is True
        assert len(result["mappings"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_ast_nodes_by_intent(self, intent_manager, mock_postgres_connection):
        """Test retrieving AST nodes by intent."""
        from datetime import datetime
        intent_manager._schema_initialized = True
        
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            ("uuid1", "node1", "source1", 0.95, '{"key": "value"}', 
             datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 0, 0)),
            ("uuid2", "node2", "source1", 0.90, None, 
             datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 1, 0, 0, 0)),
        ])
        
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        
        mock_postgres_connection.get_connection = MagicMock(return_value=mock_context)
        
        result = await intent_manager.get_ast_nodes_by_intent("intent1", "source1")
        
        assert len(result) == 2
        assert result[0]["ast_node_id"] == "node1"
        assert result[0]["confidence"] == 0.95
        assert result[0]["metadata"] == {"key": "value"}
        assert result[1]["ast_node_id"] == "node2"
        assert result[1]["metadata"] is None
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="pgvector is out of scope for this project")
    async def test_search_ast_by_intent_vector(self, intent_manager, mock_postgres_connection):
        """Test vector similarity search."""
        intent_manager._schema_initialized = True
        
        mock_conn = AsyncMock()
        # First check if table exists
        mock_conn.fetchone = AsyncMock(return_value=(True,))
        
        # Then return search results
        mock_conn.fetch = AsyncMock(return_value=[
            ("intent1", 0.95, '{"intent_key": "value"}', "node1", "source1", 
             0.9, '{"mapping_key": "value"}'),
            ("intent1", 0.95, '{"intent_key": "value"}', "node2", "source1", 
             0.85, None),
            ("intent2", 0.80, None, "node3", "source2", 1.0, None),
        ])
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_conn
        mock_context.__aexit__.return_value = None
        
        mock_postgres_connection.get_connection.return_value = mock_context
        
        result = await intent_manager.search_ast_by_intent_vector(
            intent_vector=[0.1] * 768,
            limit=10,
            threshold=0.7
        )
        
        assert len(result) == 2  # Two unique intents
        assert result[0]["intent_id"] == "intent1"
        assert result[0]["similarity"] == 0.95
        assert len(result[0]["ast_nodes"]) == 2
        assert result[1]["intent_id"] == "intent2"
        assert result[1]["similarity"] == 0.80
    
    @pytest.mark.asyncio
    async def test_remove_intent_mapping(self, intent_manager, mock_postgres_connection):
        """Test removing intent mappings."""
        intent_manager._schema_initialized = True
        
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 3")
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_conn
        mock_context.__aexit__.return_value = None
        
        mock_postgres_connection.get_connection.return_value = mock_context
        
        # Remove all mappings for an intent
        count = await intent_manager.remove_intent_mapping("intent1")
        assert count == 3
        
        # Verify vector was also deleted
        assert mock_conn.execute.call_count == 2  # Delete mappings + delete vector
    
    @pytest.mark.asyncio
    async def test_error_handling(self, intent_manager, mock_postgres_connection):
        """Test error handling in intent operations."""
        intent_manager._schema_initialized = True
        
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=Exception("Database error"))
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_conn
        mock_context.__aexit__.return_value = None
        
        mock_postgres_connection.get_connection.return_value = mock_context
        
        with pytest.raises(DataOperationError, match="Failed to get AST nodes"):
            await intent_manager.get_ast_nodes_by_intent("intent1")