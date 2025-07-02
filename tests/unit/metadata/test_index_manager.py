"""Unit tests for IndexManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_postgres_manager.metadata.index_manager import IndexManager
from graph_postgres_manager.metadata.models import IndexInfo


@pytest.fixture
def mock_connection():
    """Create a mock PostgreSQL connection."""
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.fetch_all = AsyncMock()
    connection.fetch_one = AsyncMock()
    return connection


@pytest.fixture
def index_manager(mock_connection):
    """Create an IndexManager instance with mocked connection."""
    return IndexManager(mock_connection)


@pytest.mark.asyncio
async def test_get_index_info(index_manager, mock_connection):
    """Test getting index information."""
    # Mock response
    mock_connection.fetch_all.return_value = [
        {
            "schema_name": "public",
            "table_name": "users",
            "index_name": "users_pkey",
            "is_unique": True,
            "is_primary": True,
            "is_valid": True,
            "is_ready": True,
            "is_live": True,
            "is_replica_identity": False,
            "columns": ["id"],
            "index_definition": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)",
            "size_bytes": 16384,
            "index_scans": 1000,
            "tuples_read": 5000,
            "tuples_fetched": 4500
        },
        {
            "schema_name": "public",
            "table_name": "users",
            "index_name": "users_email_idx",
            "is_unique": True,
            "is_primary": False,
            "is_valid": True,
            "is_ready": True,
            "is_live": True,
            "is_replica_identity": False,
            "columns": ["email"],
            "index_definition": "CREATE UNIQUE INDEX users_email_idx ON public.users USING btree (email)",
            "size_bytes": 32768,
            "index_scans": 500,
            "tuples_read": 2000,
            "tuples_fetched": 1800
        }
    ]
    
    indexes = await index_manager.get_index_info("public", "users")
    
    assert len(indexes) == 2
    assert isinstance(indexes[0], IndexInfo)
    assert indexes[0].index_name == "users_pkey"
    assert indexes[0].is_primary is True
    assert indexes[0].columns == ["id"]
    assert indexes[1].index_name == "users_email_idx"
    assert indexes[1].is_unique is True


@pytest.mark.asyncio
async def test_analyze_index_usage(index_manager, mock_connection):
    """Test index usage analysis."""
    # Mock get_index_info
    with patch.object(index_manager, "get_index_info") as mock_get_indexes:
        mock_get_indexes.return_value = [
            IndexInfo(
                schema_name="public",
                table_name="users",
                index_name="users_pkey",
                is_unique=True,
                is_primary=True,
                is_partial=False,
                index_definition="CREATE UNIQUE INDEX...",
                columns=["id"],
                size_bytes=16384,
                index_scans=1000
            ),
            IndexInfo(
                schema_name="public",
                table_name="users",
                index_name="unused_idx",
                is_unique=False,
                is_primary=False,
                is_partial=False,
                index_definition="CREATE INDEX...",
                columns=["created_at"],
                size_bytes=20480,
                index_scans=0  # Unused
            ),
            IndexInfo(
                schema_name="public",
                table_name="users",
                index_name="rarely_used_idx",
                is_unique=False,
                is_primary=False,
                is_partial=False,
                index_definition="CREATE INDEX...",
                columns=["status"],
                size_bytes=8192,
                index_scans=50  # Rarely used
            )
        ]
        
        # Mock table scan stats
        mock_connection.fetch_all.side_effect = [
            # Table scan stats
            [{
                "tablename": "users",
                "seq_scan": 5000,
                "seq_tup_read": 100000,
                "idx_scan": 1000,
                "idx_tup_fetch": 5000
            }],
            # Index bloat query
            []
        ]
        
        analysis = await index_manager.analyze_index_usage("public")
        
        # Check unused indexes
        assert len(analysis["unused_indexes"]) == 1
        assert analysis["unused_indexes"][0]["index_name"] == "unused_idx"
        
        # Check rarely used indexes
        assert len(analysis["rarely_used_indexes"]) == 1
        assert analysis["rarely_used_indexes"][0]["index_name"] == "rarely_used_idx"
        
        # Check recommendations
        assert len(analysis["recommendations"]) > 0
        assert any("unused indexes" in rec for rec in analysis["recommendations"])


@pytest.mark.asyncio
async def test_find_duplicate_indexes(index_manager):
    """Test finding duplicate indexes."""
    indexes = [
        IndexInfo(
            schema_name="public",
            table_name="users",
            index_name="idx_users_email",
            is_unique=False,
            is_primary=False,
            is_partial=False,
            index_definition="",
            columns=["email"]
        ),
        IndexInfo(
            schema_name="public",
            table_name="users",
            index_name="idx_users_email_duplicate",
            is_unique=False,
            is_primary=False,
            is_partial=False,
            index_definition="",
            columns=["email"]  # Same columns - exact duplicate
        ),
        IndexInfo(
            schema_name="public",
            table_name="users",
            index_name="idx_users_email_name",
            is_unique=False,
            is_primary=False,
            is_partial=False,
            index_definition="",
            columns=["email", "name"]  # First index is redundant prefix
        )
    ]
    
    duplicates = index_manager._find_duplicate_indexes(indexes)
    
    assert len(duplicates) == 2
    
    # Check exact duplicate
    exact_dup = next(d for d in duplicates if d["type"] == "exact_duplicate")
    assert exact_dup["index1"] == "idx_users_email"
    assert exact_dup["index2"] == "idx_users_email_duplicate"
    
    # Check redundant prefix
    redundant = next(d for d in duplicates if d["type"] == "redundant_prefix")
    assert redundant["redundant_index"] == "idx_users_email"
    assert redundant["covering_index"] == "idx_users_email_name"


@pytest.mark.asyncio
async def test_suggest_indexes(index_manager, mock_connection):
    """Test index suggestions."""
    # Mock current indexes (empty - no indexes)
    with patch.object(index_manager, "get_index_info") as mock_get_indexes:
        mock_get_indexes.return_value = []
        
        # Mock table stats showing high sequential scans
        mock_connection.fetch_all.return_value = [{
            "tablename": "users",
            "seq_scan": 10000,
            "seq_tup_read": 1000000,
            "idx_scan": 0,
            "idx_tup_fetch": 0
        }]
        
        suggestions = await index_manager.suggest_indexes("public")
        
        # Should suggest indexes for tables with high seq scans
        assert len(suggestions) > 0
        assert any("high_sequential_scan_ratio" in s.get("reason", "") 
                  for s in suggestions)


@pytest.mark.asyncio
async def test_create_index(index_manager, mock_connection):
    """Test creating a new index."""
    index_name = await index_manager.create_index(
        "public", 
        "users", 
        ["email"],
        unique=True,
        concurrent=True
    )
    
    assert index_name == "idx_users_email"
    
    # Verify CREATE INDEX statement was executed
    mock_connection.execute.assert_called()
    create_stmt = mock_connection.execute.call_args_list[0][0][0]
    assert "CREATE UNIQUE INDEX CONCURRENTLY" in create_stmt
    assert "idx_users_email" in create_stmt
    assert "ON public.users (email)" in create_stmt


@pytest.mark.asyncio
async def test_create_index_with_custom_name(index_manager, mock_connection):
    """Test creating an index with custom name."""
    index_name = await index_manager.create_index(
        "public",
        "users",
        ["email", "status"],
        index_name="custom_idx_name",
        unique=False,
        concurrent=False
    )
    
    assert index_name == "custom_idx_name"
    
    create_stmt = mock_connection.execute.call_args_list[0][0][0]
    assert "CREATE INDEX custom_idx_name" in create_stmt
    assert "UNIQUE" not in create_stmt
    assert "CONCURRENTLY" not in create_stmt


@pytest.mark.asyncio
async def test_check_index_bloat(index_manager, mock_connection):
    """Test checking for index bloat."""
    # Mock bloat query results
    mock_connection.fetch_all.return_value = [
        {
            "index_name": "bloated_idx",
            "tablename": "users",
            "index_size": "100 MB",
            "bloat_percentage": 45.5
        },
        {
            "index_name": "normal_idx",
            "tablename": "posts",
            "index_size": "50 MB",
            "bloat_percentage": 10.0  # Below threshold
        }
    ]
    
    bloated = await index_manager._check_index_bloat("public")
    
    # Should only return indexes with >20% bloat
    assert len(bloated) == 1
    assert bloated[0]["index_name"] == "bloated_idx"
    assert bloated[0]["bloat_percentage"] == 45.5


def test_generate_recommendations(index_manager):
    """Test recommendation generation."""
    analysis = {
        "unused_indexes": [
            {"index_name": "idx1", "size_bytes": 10 * 1024 * 1024},
            {"index_name": "idx2", "size_bytes": 5 * 1024 * 1024}
        ],
        "duplicate_indexes": [
            {"type": "exact_duplicate"}
        ],
        "index_bloat": [
            {"index_name": "bloated_idx", "bloat_percentage": 60}
        ],
        "missing_indexes": [
            {"table": "users"}
        ]
    }
    
    recommendations = index_manager._generate_recommendations(analysis)
    
    assert len(recommendations) >= 4
    assert any("unused indexes" in r for r in recommendations)
    assert any("duplicate" in r for r in recommendations)
    assert any("bloated" in r for r in recommendations)
    assert any("missing" in r for r in recommendations)


def test_clear_cache(index_manager):
    """Test clearing caches."""
    # Add some data to caches
    index_manager._index_cache["test"] = []
    index_manager._usage_stats_cache["test"] = {}
    
    assert len(index_manager._index_cache) == 1
    assert len(index_manager._usage_stats_cache) == 1
    
    index_manager.clear_cache()
    
    assert len(index_manager._index_cache) == 0
    assert len(index_manager._usage_stats_cache) == 0