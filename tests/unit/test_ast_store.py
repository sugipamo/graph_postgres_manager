"""Test cases for AST storage functionality."""

from unittest.mock import AsyncMock

import pytest

from graph_postgres_manager.exceptions import DataOperationError, ValidationError
from graph_postgres_manager.manager import GraphPostgresManager


class TestASTStore:
    """Test cases for store_ast_graph method."""

    @pytest.fixture
    def sample_ast_graph(self):
        """Sample AST graph data for testing."""
        return {
            "nodes": [
                {
                    "id": "module_1",
                    "node_type": "Module",
                    "source_id": "test_source_1"
                },
                {
                    "id": "func_1",
                    "node_type": "FunctionDef",
                    "value": "test_function",
                    "lineno": 10,
                    "source_id": "test_source_1"
                },
                {
                    "id": "name_1",
                    "node_type": "Name",
                    "value": "x",
                    "lineno": 11,
                    "source_id": "test_source_1"
                }
            ],
            "edges": [
                {
                    "source": "module_1",
                    "target": "func_1",
                    "type": "CHILD"
                },
                {
                    "source": "func_1",
                    "target": "name_1",
                    "type": "CHILD"
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_store_ast_graph_success(self, sample_ast_graph):
        """Test successful storage of AST graph."""
        manager = GraphPostgresManager()
        manager._is_initialized = True  # Mock initialized state
        
        # Mock Neo4j connection
        mock_neo4j = AsyncMock()
        # First call for nodes, second call for edges
        mock_neo4j.execute_query = AsyncMock(side_effect=[
            [{"created": 3}],  # nodes
            [{"created": 2}],  # edges
            None, None, None, None  # index creation calls
        ])
        manager._neo4j_conn = mock_neo4j
        
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="test_source_1"
        )
        
        assert result["created_nodes"] == 3
        assert result["created_edges"] == 2
        assert result["import_time_ms"] >= 0
        assert result["nodes_per_second"] > 0
        assert mock_neo4j.execute_query.call_count >= 2  # At least nodes + edges

    @pytest.mark.asyncio
    async def test_store_ast_graph_with_metadata(self, sample_ast_graph):
        """Test storing AST graph with metadata."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(side_effect=[
            [{"created": 3}],  # nodes
            [{"created": 2}],  # edges
            None, None, None, None  # index creation calls
        ])
        manager._neo4j_conn = mock_neo4j
        
        metadata = {
            "file_path": "/path/to/file.py",
            "language": "python",
            "version": "3.12"
        }
        
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="test_source_1",
            metadata=metadata
        )
        
        assert result["created_nodes"] == 3
        assert result["created_edges"] == 2

    @pytest.mark.asyncio
    async def test_store_ast_graph_validation_error_missing_nodes(self):
        """Test validation error when nodes are missing."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        invalid_graph = {"edges": []}
        
        with pytest.raises(ValidationError) as exc_info:
            await manager.store_ast_graph(
                graph_data=invalid_graph,
                source_id="test_source_1"
            )
        
        assert "Missing required field 'nodes'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_ast_graph_validation_error_invalid_node(self):
        """Test validation error for invalid node structure."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        invalid_graph = {
            "nodes": [
                {
                    "id": "node_1",
                    # Missing required field 'node_type'
                    "source_id": "test_source_1"
                }
            ],
            "edges": []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            await manager.store_ast_graph(
                graph_data=invalid_graph,
                source_id="test_source_1"
            )
        
        assert "Missing required field" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_ast_graph_validation_error_invalid_edge(self):
        """Test validation error for invalid edge structure."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        invalid_graph = {
            "nodes": [
                {
                    "id": "node_1",
                    "node_type": "Module",
                    "source_id": "test_source_1"
                }
            ],
            "edges": [
                {
                    "source": "node_1",
                    # Missing required field 'target'
                    "type": "CHILD"
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            await manager.store_ast_graph(
                graph_data=invalid_graph,
                source_id="test_source_1"
            )
        
        assert "Missing required field" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_ast_graph_validation_error_invalid_edge_type(self):
        """Test validation error for invalid edge type."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        invalid_graph = {
            "nodes": [
                {
                    "id": "node_1",
                    "node_type": "Module",
                    "source_id": "test_source_1"
                },
                {
                    "id": "node_2",
                    "node_type": "FunctionDef",
                    "source_id": "test_source_1"
                }
            ],
            "edges": [
                {
                    "source": "node_1",
                    "target": "node_2",
                    "type": "INVALID_TYPE"
                }
            ]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            await manager.store_ast_graph(
                graph_data=invalid_graph,
                source_id="test_source_1"
            )
        
        assert "Invalid edge type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_ast_graph_batch_processing(self):
        """Test batch processing for large graphs."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        # Create a large graph
        large_graph = {
            "nodes": [
                {
                    "id": f"node_{i}",
                    "node_type": "Name",
                    "value": f"var_{i}",
                    "source_id": "test_source_1"
                }
                for i in range(10000)
            ],
            "edges": [
                {
                    "source": f"node_{i}",
                    "target": f"node_{i+1}",
                    "type": "NEXT"
                }
                for i in range(9999)
            ]
        }
        
        mock_neo4j = AsyncMock()
        # Simulate multiple batch calls for nodes and edges
        side_effects = []
        # 10 batches for nodes (10000 / 1000)
        for _ in range(10):
            side_effects.append([{"created": 1000}])
        # 10 batches for edges (9999 / 1000)
        for _ in range(10):
            side_effects.append([{"created": 1000}])
        # Index creation calls
        side_effects.extend([None, None, None, None])
        
        mock_neo4j.execute_query = AsyncMock(side_effect=side_effects)
        manager._neo4j_conn = mock_neo4j
        
        result = await manager.store_ast_graph(
            graph_data=large_graph,
            source_id="test_source_1"
        )
        
        assert result["created_nodes"] == 10000
        assert result["created_edges"] == 10000  # Due to how batching works
        # Should have been called multiple times due to batching
        assert mock_neo4j.execute_query.call_count > 10

    @pytest.mark.asyncio
    async def test_store_ast_graph_error_handling(self, sample_ast_graph):
        """Test error handling during storage."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(side_effect=Exception("Neo4j error"))
        manager._neo4j_conn = mock_neo4j
        
        with pytest.raises(DataOperationError) as exc_info:
            await manager.store_ast_graph(
                graph_data=sample_ast_graph,
                source_id="test_source_1"
            )
        
        assert "Failed to store AST graph" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_ast_graph_duplicate_handling(self, sample_ast_graph):
        """Test handling of duplicate nodes."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        # Add duplicate node
        sample_ast_graph["nodes"].append({
            "id": "module_1",  # Duplicate ID
            "node_type": "Module",
            "source_id": "test_source_1"
        })
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[{"created": 3}])
        manager._neo4j_conn = mock_neo4j
        
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="test_source_1"
        )
        
        # Should handle duplicates gracefully
        assert result["created_nodes"] >= 3

    @pytest.mark.asyncio
    async def test_store_ast_graph_performance_metrics(self, sample_ast_graph):
        """Test performance metrics collection."""
        manager = GraphPostgresManager()
        manager._is_initialized = True
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[{"created": 3}])
        manager._neo4j_conn = mock_neo4j
        
        result = await manager.store_ast_graph(
            graph_data=sample_ast_graph,
            source_id="test_source_1"
        )
        
        # Should include performance metrics
        assert "import_time_ms" in result
        assert "nodes_per_second" in result
        assert result["nodes_per_second"] > 0