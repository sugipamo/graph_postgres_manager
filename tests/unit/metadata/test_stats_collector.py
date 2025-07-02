"""Unit tests for StatsCollector."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_postgres_manager.exceptions import MetadataError
from graph_postgres_manager.metadata.models import QueryPattern, TableStats
from graph_postgres_manager.metadata.stats_collector import StatsCollector


@pytest.fixture
def mock_connection():
    """Create a mock PostgreSQL connection."""
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.fetch_all = AsyncMock()
    connection.fetch_one = AsyncMock()
    return connection


@pytest.fixture
def stats_collector(mock_connection):
    """Create a StatsCollector instance with mocked connection."""
    return StatsCollector(mock_connection)


@pytest.mark.asyncio
async def test_collect_table_stats(stats_collector, mock_connection):
    """Test collecting table statistics."""
    # Mock response
    mock_connection.fetch_all.return_value = [
        {
            "schema_name": "public",
            "table_name": "users",
            "live_tuple_count": 1000,
            "dead_tuple_count": 50,
            "seq_scans": 100,
            "total_size": 8388608,  # 8MB
            "table_size": 4194304,  # 4MB
            "indexes_size": 2097152,  # 2MB
            "toast_size": 0,
            "last_vacuum": datetime.now() - timedelta(days=1),
            "last_autovacuum": datetime.now() - timedelta(hours=6),
            "last_analyze": datetime.now() - timedelta(days=2),
            "last_autoanalyze": datetime.now() - timedelta(hours=12),
            "n_tup_ins": 100,
            "n_tup_upd": 50,
            "n_tup_del": 10,
            "n_tup_hot_upd": 30,
            "vacuum_count": 5,
            "autovacuum_count": 10,
            "analyze_count": 3,
            "autoanalyze_count": 8
        }
    ]
    
    stats_list = await stats_collector.collect_table_stats("public", "users")
    
    assert len(stats_list) == 1
    stats = stats_list[0]
    assert isinstance(stats, TableStats)
    assert stats.table_name == "users"
    assert stats.row_count == 1050  # live + dead
    assert stats.live_tuple_count == 1000
    assert stats.dead_tuple_count == 50
    assert stats.total_size == 8388608
    
    # Verify stats were stored
    mock_connection.execute.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_query_patterns_no_extension(stats_collector, mock_connection):
    """Test analyzing query patterns when pg_stat_statements is not available."""
    # Mock pg_stat_statements not installed
    mock_connection.fetch_one.return_value = {"exists": False}
    
    with pytest.raises(MetadataError) as exc_info:
        await stats_collector.analyze_query_patterns()
    
    assert "pg_stat_statements extension is not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_analyze_query_patterns_success(stats_collector, mock_connection):
    """Test successful query pattern analysis."""
    # Mock pg_stat_statements exists
    mock_connection.fetch_one.return_value = {"exists": True}
    
    # Mock query patterns
    mock_connection.fetch_all.return_value = [
        {
            "query": "SELECT * FROM users WHERE id = 123",
            "calls": 1000,
            "total_time_ms": 5000,
            "mean_time_ms": 5.0,
            "min_time_ms": 1,
            "max_time_ms": 100,
            "stddev_time_ms": 10.0,
            "rows": 1000,
            "shared_blks_hit": 5000,
            "shared_blks_read": 100,
            "temp_blks_read": 0,
            "temp_blks_written": 0
        },
        {
            "query": "UPDATE posts SET title = 'New Title' WHERE id = 456",
            "calls": 500,
            "total_time_ms": 2500,
            "mean_time_ms": 5.0,
            "min_time_ms": 2,
            "max_time_ms": 50,
            "stddev_time_ms": 5.0,
            "rows": 500,
            "shared_blks_hit": 2500,
            "shared_blks_read": 50,
            "temp_blks_read": 0,
            "temp_blks_written": 0
        }
    ]
    
    patterns = await stats_collector.analyze_query_patterns()
    
    assert len(patterns) == 2
    assert isinstance(patterns[0], QueryPattern)
    
    # Check normalization
    assert patterns[0].query_template == "SELECT * FROM users WHERE id = ?"
    assert patterns[1].query_template == "UPDATE posts SET title = ? WHERE id = ?"
    
    # Check extracted tables
    assert "users" in patterns[0].tables_referenced
    assert "posts" in patterns[1].tables_referenced


def test_normalize_query(stats_collector):
    """Test query normalization."""
    test_cases = [
        (
            "SELECT * FROM users WHERE id = 123",
            "SELECT * FROM users WHERE id = ?"
        ),
        (
            "INSERT INTO logs (message, value) VALUES ('test message', 42.5)",
            "INSERT INTO logs (message, value) VALUES (?, ?)"
        ),
        (
            "SELECT * FROM orders WHERE status IN (1, 2, 3, 4, 5)",
            "SELECT * FROM orders WHERE status IN (?)"
        ),
        (
            "SELECT   *   FROM    users    WHERE   age  >  18",
            "SELECT * FROM users WHERE age > ?"
        )
    ]
    
    for original, expected in test_cases:
        normalized, hash_val = stats_collector._normalize_query(original)
        assert normalized == expected
        assert len(hash_val) == 64  # SHA256 hash length


def test_extract_table_references(stats_collector):
    """Test extracting table references from queries."""
    test_cases = [
        ("SELECT * FROM users", ["users"]),
        ("SELECT * FROM public.users", ["users"]),
        ("SELECT u.* FROM users u JOIN posts p ON u.id = p.user_id", ["users", "posts"]),
        ("UPDATE users SET name = 'test'", ["users"]),
        ("INSERT INTO logs (message) VALUES ('test')", ["logs"]),
        ("DELETE FROM old_records WHERE created < now()", ["old_records"]),
        ('SELECT * FROM "User Table"', ["User Table"])
    ]
    
    for query, expected_tables in test_cases:
        tables = stats_collector._extract_table_references(query)
        assert set(tables) == set(expected_tables)


@pytest.mark.asyncio
async def test_generate_report(stats_collector, mock_connection):
    """Test generating a comprehensive report."""
    # Mock collect_table_stats
    with patch.object(stats_collector, "collect_table_stats") as mock_collect:
        mock_collect.return_value = [
            TableStats(
                schema_name="public",
                table_name="users",
                row_count=1000,
                total_size=8388608,
                table_size=4194304,
                indexes_size=2097152,
                toast_size=0,
                dead_tuple_count=100,
                live_tuple_count=900,
                last_vacuum=datetime.now() - timedelta(days=7),
                last_analyze=datetime.now() - timedelta(days=10)
            ),
            TableStats(
                schema_name="public",
                table_name="posts",
                row_count=5000,
                total_size=16777216,
                table_size=8388608,
                indexes_size=4194304,
                toast_size=0,
                dead_tuple_count=50,
                live_tuple_count=4950
            )
        ]
        
        # Mock index summary
        mock_connection.fetch_one.return_value = {
            "total_indexes": 5,
            "unused_indexes": 1,
            "total_index_size": 6291456,
            "unique_indexes": 3,
            "primary_keys": 2
        }
        
        # Mock for pg_stat_statements check
        mock_connection.fetch_one.side_effect = [
            {"total_indexes": 5, "unused_indexes": 1, "total_index_size": 6291456,
             "unique_indexes": 3, "primary_keys": 2},
            {"exists": False}  # pg_stat_statements not available
        ]
        
        report = await stats_collector.generate_report("public", include_queries=True)
        
        # Check summary
        assert report["schema"] == "public"
        assert report["summary"]["total_tables"] == 2
        assert report["summary"]["total_rows"] == 6000
        assert report["summary"]["total_dead_tuples"] == 150
        
        # Check table details
        assert "users" in report["tables"]
        assert report["tables"]["users"]["rows"] == 1000
        assert report["tables"]["users"]["bloat_ratio"] == 0.1  # 100/1000
        
        # Check recommendations
        assert len(report["recommendations"]) > 0
        # Should recommend analyze for users table (>7 days old)
        assert any("hasn't been analyzed" in r for r in report["recommendations"])


def test_format_bytes(stats_collector):
    """Test formatting bytes to human readable format."""
    test_cases = [
        (100, "100.00 B"),
        (1024, "1.00 KB"),
        (1048576, "1.00 MB"),
        (1073741824, "1.00 GB"),
        (1099511627776, "1.00 TB"),
        (1536, "1.50 KB"),
        (2621440, "2.50 MB")
    ]
    
    for bytes_val, expected in test_cases:
        assert stats_collector._format_bytes(bytes_val) == expected


@pytest.mark.asyncio
async def test_start_continuous_collection(stats_collector, mock_connection):
    """Test continuous statistics collection."""
    # Mock successful stats collection
    with patch.object(stats_collector, "collect_table_stats") as mock_collect:
        with patch.object(stats_collector, "analyze_query_patterns") as mock_analyze:
            mock_collect.return_value = []
            mock_analyze.side_effect = MetadataError("pg_stat_statements not available")
            
            # Start collection with very short interval
            collection_task = asyncio.create_task(
                stats_collector.start_continuous_collection("public", interval_minutes=0.001)
            )
            
            # Let it run for a moment
            await asyncio.sleep(0.01)
            
            # Cancel the task
            collection_task.cancel()
            
            try:
                await collection_task
            except asyncio.CancelledError:
                pass
            
            # Verify collection was attempted
            assert mock_collect.called
            assert stats_collector._last_collection_time is not None


def test_get_last_collection_time(stats_collector):
    """Test getting last collection time."""
    # Initially None
    assert stats_collector.get_last_collection_time() is None
    
    # Set a time
    test_time = datetime.now()
    stats_collector._last_collection_time = test_time
    
    assert stats_collector.get_last_collection_time() == test_time


def test_clear_cache(stats_collector):
    """Test clearing the stats cache."""
    # Add some data to cache
    stats_collector._stats_cache["test"] = {"data": "value"}
    
    assert len(stats_collector._stats_cache) == 1
    
    stats_collector.clear_cache()
    
    assert len(stats_collector._stats_cache) == 0