"""Unit tests for SchemaManager."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from graph_postgres_manager.metadata.schema_manager import SchemaManager
from graph_postgres_manager.metadata.models import (
    TableInfo, SchemaChange, ChangeType, ObjectType, Migration, MigrationStatus
)
from graph_postgres_manager.exceptions import SchemaError, MetadataError


@pytest.fixture
def mock_connection():
    """Create a mock PostgreSQL connection."""
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.fetch_all = AsyncMock()
    connection.fetch_one = AsyncMock()
    return connection


@pytest.fixture
def schema_manager(mock_connection):
    """Create a SchemaManager instance with mocked connection."""
    return SchemaManager(mock_connection)


@pytest.mark.asyncio
async def test_initialize_metadata_schema(schema_manager, mock_connection):
    """Test metadata schema initialization."""
    # Test successful initialization
    await schema_manager.initialize_metadata_schema()
    
    # Should execute the minimal schema creation
    mock_connection.execute.assert_called_once()
    call_args = mock_connection.execute.call_args[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS _graph_postgres_metadata" in call_args


@pytest.mark.asyncio
async def test_get_tables(schema_manager, mock_connection):
    """Test getting list of tables."""
    # Mock response
    mock_connection.fetch_all.return_value = [
        {'table_name': 'users'},
        {'table_name': 'posts'},
        {'table_name': 'comments'}
    ]
    
    tables = await schema_manager._get_tables('public')
    
    assert tables == ['users', 'posts', 'comments']
    mock_connection.fetch_all.assert_called_once()
    query, params = mock_connection.fetch_all.call_args[0]
    assert 'information_schema.tables' in query
    assert params == ('public',)


@pytest.mark.asyncio
async def test_get_table_columns(schema_manager, mock_connection):
    """Test getting table column information."""
    # Mock response
    mock_connection.fetch_all.return_value = [
        {
            'column_name': 'id',
            'data_type': 'integer',
            'is_nullable': 'NO',
            'column_default': "nextval('users_id_seq'::regclass)",
            'character_maximum_length': None,
            'numeric_precision': 32,
            'numeric_scale': 0,
            'ordinal_position': 1,
            'is_primary_key': True
        },
        {
            'column_name': 'email',
            'data_type': 'character varying',
            'is_nullable': 'NO',
            'column_default': None,
            'character_maximum_length': 255,
            'numeric_precision': None,
            'numeric_scale': None,
            'ordinal_position': 2,
            'is_primary_key': False
        }
    ]
    
    columns = await schema_manager._get_table_columns('public', 'users')
    
    assert len(columns) == 2
    assert columns[0]['column_name'] == 'id'
    assert columns[0]['is_primary_key'] is True
    assert columns[1]['column_name'] == 'email'
    assert columns[1]['character_maximum_length'] == 255


@pytest.mark.asyncio
async def test_get_table_info(schema_manager, mock_connection):
    """Test getting complete table information."""
    # Mock responses for various queries
    mock_connection.fetch_all.side_effect = [
        # Columns
        [{'column_name': 'id', 'data_type': 'integer', 'is_nullable': 'NO', 
          'is_primary_key': True}],
        # Constraints
        [{'constraint_name': 'users_pkey', 'constraint_type': 'PRIMARY KEY'}],
        # Indexes
        [{'index_name': 'users_pkey', 'is_unique': True, 'is_primary': True,
          'columns': ['id'], 'index_definition': 'CREATE UNIQUE INDEX...'}],
        # Foreign keys
        [],
    ]
    
    mock_connection.fetch_one.return_value = {
        'row_count': 1000,
        'total_size': 8192,
        'last_analyzed': datetime.now()
    }
    
    table_info = await schema_manager.get_table_info('public', 'users')
    
    assert isinstance(table_info, TableInfo)
    assert table_info.schema_name == 'public'
    assert table_info.table_name == 'users'
    assert len(table_info.columns) == 1
    assert table_info.row_count == 1000
    assert table_info.size_bytes == 8192


@pytest.mark.asyncio
async def test_detect_schema_changes(schema_manager, mock_connection):
    """Test schema change detection."""
    # Mock current schema
    with patch.object(schema_manager, 'get_schema_info') as mock_get_schema:
        mock_get_schema.return_value = {
            'new_table': TableInfo(
                schema_name='public',
                table_name='new_table',
                columns=[],
                constraints=[],
                indexes=[],
                foreign_keys=[]
            )
        }
        
        # Mock last known schema (empty)
        mock_connection.fetch_all.return_value = []
        
        changes = await schema_manager.detect_schema_changes('public')
        
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.CREATE
        assert changes[0].object_type == ObjectType.TABLE
        assert changes[0].object_name == 'new_table'


@pytest.mark.asyncio
async def test_apply_migration_success(schema_manager, mock_connection):
    """Test successful migration application."""
    migration_content = "CREATE TABLE test_table (id INTEGER PRIMARY KEY);"
    
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = migration_content
        
        # Mock migration record creation
        mock_connection.fetch_one.side_effect = [
            None,  # No existing migration
            {'id': 1}  # New migration ID
        ]
        
        migration = await schema_manager.apply_migration(
            'migrations/001_test.sql',
            '001',
            'Test migration'
        )
        
        assert migration.status == MigrationStatus.COMPLETED
        assert migration.version == '001'
        assert migration.execution_time_ms is not None
        
        # Verify migration was executed
        assert mock_connection.execute.call_count >= 2  # Insert + migration SQL + update


@pytest.mark.asyncio
async def test_apply_migration_already_applied(schema_manager, mock_connection):
    """Test applying an already applied migration."""
    # Mock existing completed migration
    mock_connection.fetch_one.return_value = {
        'status': MigrationStatus.COMPLETED.value
    }
    
    with pytest.raises(SchemaError) as exc_info:
        await schema_manager.apply_migration('migrations/001_test.sql', '001')
    
    assert 'already applied' in str(exc_info.value)


@pytest.mark.asyncio
async def test_apply_migration_file_not_found(schema_manager, mock_connection):
    """Test applying migration with missing file."""
    mock_connection.fetch_one.return_value = None  # No existing migration
    
    with pytest.raises(SchemaError) as exc_info:
        await schema_manager.apply_migration('migrations/nonexistent.sql', '001')
    
    assert 'Migration file not found' in str(exc_info.value)


@pytest.mark.asyncio
async def test_apply_migration_failure(schema_manager, mock_connection):
    """Test migration failure handling."""
    migration_content = "INVALID SQL STATEMENT;"
    
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = migration_content
        
        # Mock migration record creation
        mock_connection.fetch_one.side_effect = [
            None,  # No existing migration
            {'id': 1}  # New migration ID
        ]
        
        # Make execute fail for the migration SQL
        mock_connection.execute.side_effect = [
            None,  # First call succeeds (insert)
            Exception("SQL syntax error"),  # Second call fails (migration SQL)
            None  # Third call would be the update
        ]
        
        with pytest.raises(SchemaError) as exc_info:
            await schema_manager.apply_migration('migrations/001_test.sql', '001')
        
        assert 'Migration failed' in str(exc_info.value)


def test_clear_cache(schema_manager):
    """Test clearing the schema cache."""
    # Add some data to cache
    schema_manager._schema_cache['test.table'] = TableInfo(
        schema_name='test',
        table_name='table',
        columns=[],
        constraints=[],
        indexes=[],
        foreign_keys=[]
    )
    
    assert len(schema_manager._schema_cache) == 1
    
    schema_manager.clear_cache()
    
    assert len(schema_manager._schema_cache) == 0