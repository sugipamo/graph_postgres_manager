"""Test cases for AST models."""

from dataclasses import asdict

import pytest

from graph_postgres_manager.models.ast import ASTNode, EdgeType


class TestASTNode:
    """Test cases for ASTNode model."""

    def test_create_ast_node_with_all_fields(self):
        """Test creating an ASTNode with all fields."""
        node = ASTNode(
            id="node_1",
            node_type="FunctionDef",
            value="my_function",
            lineno=10,
            source_id="src_1"
        )
        
        assert node.id == "node_1"
        assert node.node_type == "FunctionDef"
        assert node.value == "my_function"
        assert node.lineno == 10
        assert node.source_id == "src_1"

    def test_create_ast_node_minimal(self):
        """Test creating an ASTNode with minimal fields."""
        node = ASTNode(
            id="node_2",
            node_type="Module",
            source_id="src_2"
        )
        
        assert node.id == "node_2"
        assert node.node_type == "Module"
        assert node.value is None
        assert node.lineno is None
        assert node.source_id == "src_2"

    def test_ast_node_to_dict(self):
        """Test converting ASTNode to dictionary."""
        node = ASTNode(
            id="node_3",
            node_type="Name",
            value="variable_name",
            lineno=25,
            source_id="src_3"
        )
        
        node_dict = asdict(node)
        
        assert node_dict == {
            "id": "node_3",
            "node_type": "Name",
            "value": "variable_name",
            "lineno": 25,
            "source_id": "src_3"
        }

    def test_ast_node_to_cypher_properties(self):
        """Test converting ASTNode to Cypher properties."""
        node = ASTNode(
            id="node_4",
            node_type="ClassDef",
            value="MyClass",
            lineno=100,
            source_id="src_4"
        )
        
        props = node.to_cypher_properties()
        
        assert props == {
            "id": "node_4",
            "node_type": "ClassDef",
            "value": "MyClass",
            "lineno": 100,
            "source_id": "src_4"
        }

    def test_ast_node_to_cypher_properties_with_none_values(self):
        """Test converting ASTNode to Cypher properties with None values."""
        node = ASTNode(
            id="node_5",
            node_type="Module",
            source_id="src_5"
        )
        
        props = node.to_cypher_properties()
        
        # None values should be excluded
        assert props == {
            "id": "node_5",
            "node_type": "Module",
            "source_id": "src_5"
        }

    def test_ast_node_equality(self):
        """Test ASTNode equality comparison."""
        node1 = ASTNode(
            id="node_6",
            node_type="FunctionDef",
            value="func",
            lineno=50,
            source_id="src_6"
        )
        
        node2 = ASTNode(
            id="node_6",
            node_type="FunctionDef",
            value="func",
            lineno=50,
            source_id="src_6"
        )
        
        node3 = ASTNode(
            id="node_7",
            node_type="FunctionDef",
            value="func",
            lineno=50,
            source_id="src_6"
        )
        
        assert node1 == node2
        assert node1 != node3


class TestEdgeType:
    """Test cases for EdgeType enum."""

    def test_edge_type_values(self):
        """Test EdgeType enum values."""
        assert EdgeType.CHILD.value == "CHILD"
        assert EdgeType.NEXT.value == "NEXT"
        assert EdgeType.DEPENDS_ON.value == "DEPENDS_ON"

    def test_edge_type_from_string(self):
        """Test creating EdgeType from string."""
        assert EdgeType("CHILD") == EdgeType.CHILD
        assert EdgeType("NEXT") == EdgeType.NEXT
        assert EdgeType("DEPENDS_ON") == EdgeType.DEPENDS_ON

    def test_edge_type_invalid_value(self):
        """Test creating EdgeType with invalid value."""
        with pytest.raises(ValueError):
            EdgeType("INVALID_TYPE")

    def test_edge_type_iteration(self):
        """Test iterating over EdgeType values."""
        edge_types = list(EdgeType)
        assert len(edge_types) == 3
        assert EdgeType.CHILD in edge_types
        assert EdgeType.NEXT in edge_types
        assert EdgeType.DEPENDS_ON in edge_types