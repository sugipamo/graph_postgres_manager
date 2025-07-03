"""Integration tests for search functionality."""

import pytest

from graph_postgres_manager import SearchQuery, SearchType


class TestSearchIntegration:
    """Integration tests for unified search functionality."""
    
    @pytest.fixture
    async def prepared_data(self, manager):
        """Prepare test data in both databases."""
        # Store AST graph
        ast_graph = {
            "nodes": [
                {"id": "mod1", "node_type": "Module", "source_id": "test_file.py"},
                {"id": "func1", "node_type": "FunctionDef", "value": "calculate_sum", "lineno": 10},
                {"id": "func2", "node_type": "FunctionDef", "value": "calculate_product", "lineno": 20},
                {"id": "class1", "node_type": "ClassDef", "value": "Calculator", "lineno": 30},
            ],
            "edges": [
                {"source": "mod1", "target": "func1", "type": "CHILD"},
                {"source": "mod1", "target": "func2", "type": "CHILD"},
                {"source": "mod1", "target": "class1", "type": "CHILD"},
            ]
        }
        
        await manager.store_ast_graph(ast_graph, "test_file.py")
        
        # Link intents
        await manager.link_intent_to_ast(
            intent_id="sum_intent",
            ast_node_ids=["func1"],
            source_id="test_file.py",
            confidence=0.95,
            intent_vector=[0.1] * 768
        )
        
        await manager.link_intent_to_ast(
            intent_id="math_intent",
            ast_node_ids=["func1", "func2", "class1"],
            source_id="test_file.py",
            confidence=0.85,
            intent_vector=[0.2] * 768
        )
        
        yield
        
        # Cleanup
        await manager.neo4j.execute_query("MATCH (n:ASTNode) WHERE n.source_id = 'test_file.py' DETACH DELETE n")
        await manager.remove_intent_mapping("sum_intent")
        await manager.remove_intent_mapping("math_intent")
    
    @pytest.mark.asyncio
    async def test_search_by_function_name(self, manager, prepared_data):
        """Test searching for functions by name."""
        results = await manager.search_unified(
            query="calculate",
            include_graph=True,
            include_vector=False,
            include_text=False,
            max_results=10
        )
        
        assert len(results) >= 2
        
        # Check that we found both calculate functions
        function_names = {r.content for r in results if r.content}
        assert "calculate_sum" in function_names
        assert "calculate_product" in function_names
    
    @pytest.mark.asyncio
    async def test_search_by_node_type_filter(self, manager, prepared_data):
        """Test searching with node type filter."""
        results = await manager.search_unified(
            query="",  # Empty query should still work with filters
            filters={"node_types": ["FunctionDef"]},
            include_graph=True,
            include_vector=False,
            include_text=False,
            max_results=10
        )
        
        assert len(results) == 2
        assert all(r.node_type == "FunctionDef" for r in results)
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="pgvector is out of scope for this project")
    async def test_vector_search_with_intent(self, manager, prepared_data):
        """Test vector similarity search."""
        # Search with a vector similar to sum_intent
        search_vector = [0.11] * 768  # Slightly different from [0.1] * 768
        
        results = await manager.search_unified(
            query="sum",
            vector=search_vector,
            include_graph=False,
            include_vector=True,
            include_text=False,
            max_results=5
        )
        
        # Should find results through intent vectors
        assert len(results) > 0
        assert results[0].search_type == SearchType.VECTOR
    
    @pytest.mark.asyncio
    async def test_unified_search_all_types(self, manager, prepared_data):
        """Test unified search across all search types."""
        search_vector = [0.15] * 768
        
        results = await manager.search_unified(
            query="calculate",
            vector=search_vector,
            include_graph=True,
            include_vector=True,
            include_text=True,
            max_results=20
        )
        
        # Should have results from at least graph search
        assert len(results) > 0
        
        # Check for different search types
        search_types = {r.search_type for r in results}
        assert SearchType.GRAPH in search_types or SearchType.UNIFIED in search_types
    
    @pytest.mark.asyncio
    async def test_search_with_searchquery_object(self, manager, prepared_data):
        """Test search using SearchQuery object directly."""
        from graph_postgres_manager import SearchFilter
        
        query = SearchQuery(
            query="Calculator",
            search_types=[SearchType.GRAPH],
            filters=SearchFilter(
                node_types=["ClassDef"],
                source_ids=["test_file.py"],
                max_results=5
            )
        )
        
        results = await manager.search_unified(query)
        
        assert len(results) == 1
        assert results[0].content == "Calculator"
        assert results[0].node_type == "ClassDef"
    
    @pytest.mark.asyncio 
    async def test_search_score_ranking(self, manager, prepared_data):
        """Test that results are properly ranked by score."""
        results = await manager.search_unified(
            query="calculate_sum",  # Exact match should score higher
            include_graph=True,
            include_vector=False,
            include_text=False,
            max_results=10
        )
        
        assert len(results) >= 1
        
        # Exact match should be first
        assert results[0].content == "calculate_sum"
        assert results[0].score > 0.8  # High score for exact match
        
        # Other results should have lower scores
        if len(results) > 1:
            assert all(results[0].score >= r.score for r in results[1:])
    
    @pytest.mark.asyncio
    async def test_empty_search_results(self, manager, prepared_data):
        """Test search with no matching results."""
        results = await manager.search_unified(
            query="nonexistent_function_name_xyz",
            include_graph=True,
            include_vector=False,
            include_text=False,
            max_results=10
        )
        
        # May return results with low scores, but they should be low
        if results:
            assert all(r.score < 0.5 for r in results)