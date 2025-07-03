"""Unit tests for SearchManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from graph_postgres_manager.exceptions import DataOperationError
from graph_postgres_manager.search import (
    SearchFilter,
    SearchManager,
    SearchQuery,
    SearchResult,
    SearchType,
)


class TestSearchManager:
    """Test cases for SearchManager."""
    
    @pytest.fixture
    def mock_neo4j_connection(self):
        """Create a mock Neo4j connection."""
        mock = MagicMock()
        mock.execute_query = AsyncMock()
        return mock
    
    @pytest.fixture
    def mock_postgres_connection(self):
        """Create a mock PostgreSQL connection."""
        mock = MagicMock()
        mock.execute_query = AsyncMock()
        mock.get_connection = MagicMock()
        return mock
    
    
    @pytest.fixture
    def search_manager(self, mock_neo4j_connection, mock_postgres_connection):
        """Create a SearchManager instance with mocked dependencies."""
        return SearchManager(
            neo4j_connection=mock_neo4j_connection,
            postgres_connection=mock_postgres_connection
        )
    
    @pytest.mark.asyncio
    async def test_graph_search(self, search_manager, mock_neo4j_connection):
        """Test graph search functionality."""
        # Mock Neo4j response
        mock_neo4j_connection.execute_query.return_value = [
            {
                "id": "node1",
                "source_id": "source1",
                "node_type": "FunctionDef",
                "value": "test_function",
                "lineno": 10,
                "metadata": {},
                "file_path": "/test/file.py"
            }
        ]
        
        query = SearchQuery(
            query="test_function",
            search_types=[SearchType.GRAPH],
            filters=SearchFilter(max_results=10)
        )
        
        results = await search_manager.search(query)
        
        assert len(results) == 1
        assert results[0].id == "node1"
        assert results[0].source_id == "source1"
        assert results[0].node_type == "FunctionDef"
        assert results[0].content == "test_function"
        assert results[0].search_type == SearchType.GRAPH
        assert results[0].file_path == "/test/file.py"
        assert results[0].line_number == 10
    
    
    @pytest.mark.asyncio
    async def test_text_search(self, search_manager, mock_postgres_connection):
        """Test text search functionality."""
        # Mock execute_query response
        mock_postgres_connection.execute_query.return_value = [
            {
                "id": "text1",
                "source_id": "source1",
                "content": "This is a test document",
                "metadata": '{"type": "doc"}',
                "rank": 0.8
            }
        ]
        
        query = SearchQuery(
            query="test document",
            search_types=[SearchType.TEXT]
        )
        
        results = await search_manager.search(query)
        
        assert len(results) == 1
        assert results[0].id == "text1"
        assert results[0].source_id == "source1"
        assert results[0].content == "This is a test document"
        assert results[0].search_type == SearchType.TEXT
        assert results[0].metadata == {"type": "doc"}
    
    @pytest.mark.asyncio
    async def test_unified_search(self, search_manager, mock_neo4j_connection, mock_postgres_connection):
        """Test unified search across graph and text types."""
        # Mock Neo4j response
        mock_neo4j_connection.execute_query.return_value = [
            {"id": "graph1", "source_id": "source1", "value": "test", "node_type": "Function"}
        ]
        
        # Mock PostgreSQL response
        mock_postgres_connection.execute_query.return_value = [
            {"id": "text1", "source_id": "source1", "content": "test content", "metadata": "{}", "rank": 0.7}
        ]
        
        query = SearchQuery(
            query="test",
            search_types=[SearchType.UNIFIED]
        )
        
        results = await search_manager.search(query)
        
        # Should have results from graph and text sources
        assert len(results) >= 2  # At least graph and text results
        
        # Results should be ranked by score
        for i in range(1, len(results)):
            assert results[i-1].score >= results[i].score
    
    @pytest.mark.asyncio
    async def test_search_error_handling(self, search_manager, mock_neo4j_connection):
        """Test error handling in search."""
        mock_neo4j_connection.execute_query.side_effect = Exception("Neo4j error")
        
        query = SearchQuery(query="test", search_types=[SearchType.GRAPH])
        
        # Search should handle errors gracefully and return empty results
        results = await search_manager.search(query)
        assert results == []
        
        # Test that _graph_search directly raises the error
        with pytest.raises(DataOperationError, match="Graph search failed"):
            await search_manager._graph_search(query)
    
    @pytest.mark.asyncio
    async def test_result_ranking(self, search_manager):
        """Test result ranking and deduplication."""
        # Create test results
        results = [
            SearchResult(id="1", source_id="s1", score=0.5, search_type=SearchType.GRAPH),
            SearchResult(id="2", source_id="s1", score=0.8, search_type=SearchType.TEXT),
            SearchResult(id="1", source_id="s1", score=0.6, search_type=SearchType.TEXT),  # Duplicate
            SearchResult(id="3", source_id="s1", score=0.7, search_type=SearchType.GRAPH),
        ]
        
        query = SearchQuery(query="test")
        ranked = search_manager._rank_results(results, query)
        
        # Should have 3 unique results (id=1 was duplicated)
        assert len(ranked) == 3
        
        # Should be sorted by score
        assert ranked[0].id == "2"  # score 0.8
        assert ranked[1].id == "3"  # score 0.7
        assert ranked[2].id == "1"  # combined score
        
        # Duplicate should have unified type
        duplicate_result = next(r for r in ranked if r.id == "1")
        assert duplicate_result.search_type == SearchType.UNIFIED
    
    def test_cache_clear(self, search_manager):
        """Test cache clearing."""
        # Add some fake cache data
        search_manager._search_cache["test_key"] = []
        
        # Clear cache
        search_manager.clear_cache()
        
        assert len(search_manager._search_cache) == 0