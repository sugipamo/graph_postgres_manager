"""Unit tests for search models."""

import pytest

from graph_postgres_manager.search.models import SearchFilter, SearchQuery, SearchResult, SearchType


class TestSearchModels:
    """Test search model classes."""
    
    def test_search_filter_defaults(self):
        """Test SearchFilter default values."""
        filter_obj = SearchFilter()
        
        assert filter_obj.node_types is None
        assert filter_obj.source_ids is None
        assert filter_obj.file_patterns is None
        assert filter_obj.date_from is None
        assert filter_obj.date_to is None
        assert filter_obj.min_confidence == 0.0
        assert filter_obj.max_results == 100
        assert filter_obj.metadata_filters == {}
    
    def test_search_filter_validation(self):
        """Test SearchFilter validation."""
        # Invalid min_confidence
        with pytest.raises(ValueError, match="min_confidence must be between"):
            SearchFilter(min_confidence=1.5)
        
        with pytest.raises(ValueError, match="min_confidence must be between"):
            SearchFilter(min_confidence=-0.1)
        
        # Invalid max_results
        with pytest.raises(ValueError, match="max_results must be at least 1"):
            SearchFilter(max_results=0)
    
    def test_search_query_defaults(self):
        """Test SearchQuery default values."""
        query = SearchQuery(query="test")
        
        assert query.query == "test"
        assert query.search_types == [SearchType.UNIFIED]
        assert isinstance(query.filters, SearchFilter)
        assert query.vector is None
        assert query.weights == {
            SearchType.GRAPH: 0.4,
            SearchType.VECTOR: 0.4,
            SearchType.TEXT: 0.2
        }
    
    def test_search_query_validation(self):
        """Test SearchQuery validation."""
        # No query or vector
        with pytest.raises(ValueError, match="Either query text, vector, or node type filters must be provided"):
            SearchQuery(query="")
        
        # Invalid vector dimensions
        with pytest.raises(ValueError, match="Vector must have exactly 768 dimensions"):
            SearchQuery(query="test", vector=[1.0, 2.0, 3.0])
    
    def test_search_query_weight_normalization(self):
        """Test weight normalization in SearchQuery."""
        query = SearchQuery(
            query="test",
            weights={
                SearchType.GRAPH: 2.0,
                SearchType.VECTOR: 2.0,
                SearchType.TEXT: 1.0
            }
        )
        
        # Weights should be normalized to sum to 1.0
        assert abs(query.weights[SearchType.GRAPH] - 0.4) < 0.001
        assert abs(query.weights[SearchType.VECTOR] - 0.4) < 0.001
        assert abs(query.weights[SearchType.TEXT] - 0.2) < 0.001
    
    def test_search_result_defaults(self):
        """Test SearchResult default values."""
        result = SearchResult(
            id="test_id",
            source_id="source1"
        )
        
        assert result.id == "test_id"
        assert result.source_id == "source1"
        assert result.node_type is None
        assert result.content is None
        assert result.score == 0.0
        assert result.search_type == SearchType.UNIFIED
        assert result.metadata == {}
        assert result.highlights == []
        assert result.file_path is None
        assert result.line_number is None
    
    def test_search_result_score_normalization(self):
        """Test score normalization in SearchResult."""
        # Score too high
        result = SearchResult(id="test", source_id="source", score=1.5)
        assert result.score == 1.0
        
        # Score too low
        result = SearchResult(id="test", source_id="source", score=-0.5)
        assert result.score == 0.0
        
        # Valid score
        result = SearchResult(id="test", source_id="source", score=0.75)
        assert result.score == 0.75
    
    def test_search_type_enum(self):
        """Test SearchType enum values."""
        assert SearchType.GRAPH.value == "graph"
        assert SearchType.VECTOR.value == "vector"
        assert SearchType.TEXT.value == "text"
        assert SearchType.UNIFIED.value == "unified"