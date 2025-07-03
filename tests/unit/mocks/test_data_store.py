"""Unit tests for InMemoryDataStore."""

import time

import pytest

from graph_postgres_manager.mocks.data_store import InMemoryDataStore


class TestInMemoryDataStore:
    """Test InMemoryDataStore implementation."""
    
    def test_initialization(self):
        """Test data store initialization."""
        store = InMemoryDataStore()
        
        # Check initial state
        assert len(store.nodes) == 0
        assert len(store.relationships) == 0
        assert len(store.tables) == 0
        assert store.query_count == 0
    
    def test_node_operations(self):
        """Test node creation and retrieval."""
        store = InMemoryDataStore()
        
        # Create a node
        node_id = store.create_node(
            labels=["Person", "Employee"],
            properties={"name": "John", "age": 30}
        )
        
        assert node_id is not None
        assert len(store.nodes) == 1
        
        # Get node
        node = store.get_node(node_id)
        assert node is not None
        assert node["id"] == node_id
        assert "Person" in node["labels"]
        assert "Employee" in node["labels"]
        assert node["properties"]["name"] == "John"
        assert node["properties"]["age"] == 30
        
        # Get non-existent node
        assert store.get_node("non-existent") is None
    
    def test_label_indexing(self):
        """Test label-based indexing."""
        store = InMemoryDataStore()
        
        # Create nodes with different labels
        store.create_node(["Person"], {"name": "Alice"})
        store.create_node(["Person", "Manager"], {"name": "Bob"})
        store.create_node(["Department"], {"name": "IT"})
        
        # Test label queries
        persons = store.get_nodes_by_label("Person")
        assert len(persons) == 2
        assert all(p["properties"]["name"] in ["Alice", "Bob"] for p in persons)
        
        managers = store.get_nodes_by_label("Manager")
        assert len(managers) == 1
        assert managers[0]["properties"]["name"] == "Bob"
        
        departments = store.get_nodes_by_label("Department")
        assert len(departments) == 1
        assert departments[0]["properties"]["name"] == "IT"
    
    def test_relationship_operations(self):
        """Test relationship creation and retrieval."""
        store = InMemoryDataStore()
        
        # Create nodes
        person_id = store.create_node(["Person"], {"name": "Alice"})
        dept_id = store.create_node(["Department"], {"name": "Engineering"})
        
        # Create relationship
        rel_id = store.create_relationship(
            source_id=person_id,
            target_id=dept_id,
            rel_type="WORKS_IN",
            properties={"since": 2020}
        )
        
        assert rel_id == 0  # First relationship
        assert len(store.relationships) == 1
        
        # Get relationships for nodes
        person_rels = store.get_relationships_for_node(person_id)
        assert len(person_rels) == 1
        assert person_rels[0]["type"] == "WORKS_IN"
        assert person_rels[0]["properties"]["since"] == 2020
        
        dept_rels = store.get_relationships_for_node(dept_id)
        assert len(dept_rels) == 1
        assert dept_rels[0]["source"] == person_id
        assert dept_rels[0]["target"] == dept_id
    
    def test_relationship_validation(self):
        """Test relationship validation."""
        store = InMemoryDataStore()
        
        # Try to create relationship with non-existent nodes
        with pytest.raises(ValueError, match="Source node"):
            store.create_relationship("invalid1", "invalid2", "TEST")
        
        # Create one node
        node_id = store.create_node(["Node"], {})
        
        # Try with one valid, one invalid
        with pytest.raises(ValueError, match="Target node"):
            store.create_relationship(node_id, "invalid", "TEST")
    
    def test_table_operations(self):
        """Test PostgreSQL-like table operations."""
        store = InMemoryDataStore()
        
        # Create table
        store.create_table("users", {
            "id": "integer",
            "name": "text",
            "email": "text"
        })
        
        assert "users" in store.schemas
        assert store.schemas["users"]["name"] == "text"
        
        # Insert records
        store.insert_record("users", {
            "name": "Alice",
            "email": "alice@example.com"
        })
        
        store.insert_record("users", {
            "name": "Bob",
            "email": "bob@example.com"
        })
        
        # Auto-generated IDs
        records = store.get_records("users")
        assert len(records) == 2
        assert records[0]["id"] == 1
        assert records[1]["id"] == 2
    
    def test_record_queries(self):
        """Test record querying with conditions."""
        store = InMemoryDataStore()
        
        # Setup
        store.create_table("products", {"id": "integer", "name": "text", "price": "numeric"})
        store.insert_record("products", {"name": "Laptop", "price": 1000})
        store.insert_record("products", {"name": "Mouse", "price": 20})
        store.insert_record("products", {"name": "Keyboard", "price": 50})
        
        # Query all
        all_products = store.get_records("products")
        assert len(all_products) == 3
        
        # Query with WHERE
        cheap_products = store.get_records("products", where={"price": 20})
        assert len(cheap_products) == 1
        assert cheap_products[0]["name"] == "Mouse"
        
        # Query with LIMIT
        limited = store.get_records("products", limit=2)
        assert len(limited) == 2
        
        # Query with OFFSET and LIMIT
        paginated = store.get_records("products", offset=1, limit=2)
        assert len(paginated) == 2
        assert paginated[0]["name"] == "Mouse"
    
    def test_record_updates(self):
        """Test record update operations."""
        store = InMemoryDataStore()
        
        # Setup
        store.create_table("items", {"id": "integer", "name": "text", "status": "text"})
        store.insert_record("items", {"name": "Item1", "status": "active"})
        store.insert_record("items", {"name": "Item2", "status": "active"})
        store.insert_record("items", {"name": "Item3", "status": "inactive"})
        
        # Update records
        updated = store.update_records(
            "items",
            {"status": "archived"},
            where={"status": "inactive"}
        )
        
        assert updated == 1
        
        # Verify update
        items = store.get_records("items")
        archived = [i for i in items if i["status"] == "archived"]
        assert len(archived) == 1
        assert archived[0]["name"] == "Item3"
    
    def test_record_deletion(self):
        """Test record deletion."""
        store = InMemoryDataStore()
        
        # Setup
        store.create_table("temp", {"id": "integer", "value": "text"})
        for i in range(5):
            store.insert_record("temp", {"value": f"val{i}"})
        
        # Delete specific records
        deleted = store.delete_records("temp", where={"value": "val2"})
        assert deleted == 1
        
        # Verify deletion
        remaining = store.get_records("temp")
        assert len(remaining) == 4
        assert not any(r["value"] == "val2" for r in remaining)
    
    def test_text_search(self):
        """Test text search functionality."""
        store = InMemoryDataStore()
        
        # Create nodes with text content
        id1 = store.create_node(["Document"], {
            "title": "Python Programming Guide",
            "content": "Learn Python programming basics"
        })
        
        id2 = store.create_node(["Document"], {
            "title": "Java Tutorial",
            "content": "Java programming for beginners"
        })
        
        store.create_node(["Document"], {
            "title": "Database Design",
            "content": "SQL and NoSQL databases"
        })
        
        # Search for "programming"
        results = store.search_text("programming")
        assert len(results) == 2
        assert id1 in results
        assert id2 in results
        
        # Search for "Python"
        results = store.search_text("Python")
        assert len(results) == 1
        assert id1 in results
        
        # Multi-word search
        results = store.search_text("programming basics")
        assert len(results) == 1
        assert id1 in results
    
    def test_transaction_management(self):
        """Test transaction operations."""
        store = InMemoryDataStore()
        
        # Begin transaction
        tx_id = "tx-123"
        store.begin_transaction(tx_id)
        
        assert tx_id in store.active_transactions
        assert store.active_transactions[tx_id]["status"] == "active"
        
        # Add operations
        store.add_transaction_operation(tx_id, {
            "type": "create_node",
            "data": {"labels": ["Test"], "properties": {}}
        })
        
        assert len(store.active_transactions[tx_id]["operations"]) == 1
        
        # Commit transaction
        store.commit_transaction(tx_id)
        
        assert tx_id not in store.active_transactions
        assert len(store.transaction_log) == 1
        assert store.transaction_log[0]["status"] == "committed"
    
    def test_transaction_rollback(self):
        """Test transaction rollback."""
        store = InMemoryDataStore()
        
        tx_id = "tx-rollback"
        store.begin_transaction(tx_id)
        
        # Add some operations
        store.add_transaction_operation(tx_id, {"type": "test"})
        
        # Rollback
        store.rollback_transaction(tx_id)
        
        assert tx_id not in store.active_transactions
        assert len(store.transaction_log) == 1
        assert store.transaction_log[0]["status"] == "rolled_back"
    
    def test_statistics(self):
        """Test statistics collection."""
        store = InMemoryDataStore()
        
        # Perform various operations
        store.create_node(["Node"], {})
        store.create_table("test", {"id": "integer"})
        store.record_operation_time(0.01)
        store.record_operation_time(0.02)
        
        stats = store.get_stats()
        
        assert stats["nodes_count"] == 1
        assert stats["tables_count"] == 1
        assert stats["query_count"] == 2
        assert stats["avg_operation_time"] == 0.015
        assert stats["uptime_seconds"] > 0
    
    def test_clear_functionality(self):
        """Test data clearing."""
        store = InMemoryDataStore()
        
        # Add various data
        store.create_node(["Node"], {"data": "test"})
        store.create_table("table1", {"col": "type"})
        store.insert_record("table1", {"col": "value"})
        store.begin_transaction("tx1")
        
        # Clear everything
        store.clear()
        
        # Verify all data is cleared
        assert len(store.nodes) == 0
        assert len(store.tables) == 0
        assert len(store.active_transactions) == 0
        assert store.query_count == 0
    
    def test_performance(self):
        """Test performance characteristics."""
        store = InMemoryDataStore()
        
        # Create many nodes quickly
        start_time = time.time()
        for i in range(1000):
            store.create_node(["Node"], {"index": i})
        node_creation_time = time.time() - start_time
        
        # Should be very fast (< 100ms for 1000 nodes)
        assert node_creation_time < 0.1
        
        # Search should also be fast
        start_time = time.time()
        results = store.get_nodes_by_label("Node")
        search_time = time.time() - start_time
        
        assert len(results) == 1000
        assert search_time < 0.01  # < 10ms