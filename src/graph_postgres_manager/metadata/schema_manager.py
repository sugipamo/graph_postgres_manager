"""Schema management functionality for PostgreSQL."""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any

from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import MetadataError, SchemaError
from graph_postgres_manager.metadata.models import (
    ChangeType,
    Migration,
    MigrationStatus,
    ObjectType,
    SchemaChange,
    TableInfo,
)


class SchemaManager:
    """Manages PostgreSQL schema information and migrations."""
    
    def __init__(self, connection: PostgresConnection):
        """Initialize the schema manager.
        
        Args:
            connection: PostgreSQL connection instance
        """
        self.connection = connection
        self._schema_cache: dict[str, TableInfo] = {}
        self._migration_lock = asyncio.Lock()
    
    async def initialize_metadata_schema(self) -> None:
        """Initialize the metadata schema if it doesn't exist."""
        init_script_path = "scripts/init-metadata.sql"
        try:
            with open(init_script_path) as f:
                init_sql = f.read()
            
            await self.connection.execute(init_sql)
        except FileNotFoundError:
            # If script not found, create minimal schema
            await self._create_minimal_metadata_schema()
        except Exception as e:
            raise MetadataError(f"Failed to initialize metadata schema: {e}")
    
    async def _create_minimal_metadata_schema(self) -> None:
        """Create minimal metadata schema without script file."""
        create_schema_sql = """
        CREATE SCHEMA IF NOT EXISTS _graph_postgres_metadata;
        
        CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.schema_versions (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) NOT NULL UNIQUE,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checksum VARCHAR(64)
        );
        
        CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.schema_change_log (
            id SERIAL PRIMARY KEY,
            change_type VARCHAR(50) NOT NULL,
            object_type VARCHAR(50) NOT NULL,
            schema_name VARCHAR(255),
            object_name VARCHAR(255) NOT NULL,
            parent_object VARCHAR(255),
            old_definition TEXT,
            new_definition TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            change_details JSONB
        );
        """
        await self.connection.execute(create_schema_sql)
    
    async def get_schema_info(self, schema_name: str = "public") -> dict[str, TableInfo]:
        """Get complete schema information.
        
        Args:
            schema_name: Name of the schema to inspect
            
        Returns:
            Dictionary mapping table names to TableInfo objects
        """
        tables = await self._get_tables(schema_name)
        schema_info = {}
        
        for table_name in tables:
            table_info = await self.get_table_info(schema_name, table_name)
            schema_info[table_name] = table_info
            
        return schema_info
    
    async def get_table_info(self, schema_name: str, table_name: str) -> TableInfo:
        """Get detailed information about a specific table.
        
        Args:
            schema_name: Schema containing the table
            table_name: Name of the table
            
        Returns:
            TableInfo object with complete table metadata
        """
        cache_key = f"{schema_name}.{table_name}"
        if cache_key in self._schema_cache:
            return self._schema_cache[cache_key]
        
        # Get columns
        columns = await self._get_table_columns(schema_name, table_name)
        
        # Get constraints
        constraints = await self._get_table_constraints(schema_name, table_name)
        
        # Get indexes
        indexes = await self._get_table_indexes(schema_name, table_name)
        
        # Get foreign keys
        foreign_keys = await self._get_table_foreign_keys(schema_name, table_name)
        
        # Get table statistics
        stats = await self._get_table_statistics(schema_name, table_name)
        
        table_info = TableInfo(
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
            constraints=constraints,
            indexes=indexes,
            foreign_keys=foreign_keys,
            row_count=stats.get("row_count"),
            size_bytes=stats.get("total_size"),
            last_analyzed=stats.get("last_analyzed")
        )
        
        self._schema_cache[cache_key] = table_info
        return table_info
    
    async def _get_tables(self, schema_name: str) -> list[str]:
        """Get list of tables in a schema."""
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = %s 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        result = await self.connection.fetch_all(query, (schema_name,))
        return [row["table_name"] for row in result]
    
    async def _get_table_columns(self, schema_name: str, table_name: str) -> list[dict[str, Any]]:
        """Get column information for a table."""
        query = """
        SELECT 
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.ordinal_position,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
        FROM information_schema.columns c
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
                ON tc.constraint_name = ku.constraint_name
                AND tc.table_schema = ku.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = %s
                AND tc.table_name = %s
        ) pk ON c.column_name = pk.column_name
        WHERE c.table_schema = %s
        AND c.table_name = %s
        ORDER BY c.ordinal_position
        """
        result = await self.connection.fetch_all(
            query, 
            (schema_name, table_name, schema_name, table_name)
        )
        return [dict(row) for row in result]
    
    async def _get_table_constraints(
        self, schema_name: str, table_name: str
    ) -> list[dict[str, Any]]:
        """Get constraint information for a table."""
        query = """
        SELECT 
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            cc.check_clause
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        LEFT JOIN information_schema.check_constraints cc
            ON tc.constraint_name = cc.constraint_name
            AND tc.table_schema = cc.constraint_schema
        WHERE tc.table_schema = %s
        AND tc.table_name = %s
        """
        result = await self.connection.fetch_all(query, (schema_name, table_name))
        return [dict(row) for row in result]
    
    async def _get_table_indexes(self, schema_name: str, table_name: str) -> list[dict[str, Any]]:
        """Get index information for a table."""
        query = """
        SELECT 
            i.relname as index_name,
            idx.indisunique as is_unique,
            idx.indisprimary as is_primary,
            idx.indisvalid as is_valid,
            idx.indisready as is_ready,
            array_agg(a.attname ORDER BY array_position(idx.indkey, a.attnum)) as columns,
            pg_get_indexdef(idx.indexrelid) as index_definition,
            pg_size_pretty(pg_relation_size(idx.indexrelid)) as size,
            pg_relation_size(idx.indexrelid) as size_bytes
        FROM pg_index idx
        JOIN pg_class i ON i.oid = idx.indexrelid
        JOIN pg_class t ON t.oid = idx.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(idx.indkey)
        WHERE n.nspname = %s
        AND t.relname = %s
        GROUP BY i.relname, idx.indisunique, idx.indisprimary, idx.indisvalid, 
                 idx.indisready, idx.indexrelid
        """
        result = await self.connection.fetch_all(query, (schema_name, table_name))
        return [dict(row) for row in result]
    
    async def _get_table_foreign_keys(
        self, schema_name: str, table_name: str
    ) -> list[dict[str, Any]]:
        """Get foreign key information for a table."""
        query = """
        SELECT 
            tc.constraint_name,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            rc.update_rule,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
            AND tc.table_schema = rc.constraint_schema
        WHERE tc.table_schema = %s
        AND tc.table_name = %s
        AND tc.constraint_type = 'FOREIGN KEY'
        """
        result = await self.connection.fetch_all(query, (schema_name, table_name))
        return [dict(row) for row in result]
    
    async def _get_table_statistics(self, schema_name: str, table_name: str) -> dict[str, Any]:
        """Get table statistics."""
        query = """
        SELECT 
            n_live_tup as row_count,
            pg_total_relation_size(c.oid) as total_size,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables st
        JOIN pg_class c ON c.relname = st.relname
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        AND st.relname = %s
        """
        result = await self.connection.fetch_one(query, (schema_name, table_name))
        if result:
            return dict(result)
        return {}
    
    async def detect_schema_changes(self, schema_name: str = "public") -> list[SchemaChange]:
        """Detect changes in the database schema.
        
        Args:
            schema_name: Schema to monitor for changes
            
        Returns:
            List of detected schema changes
        """
        current_schema = await self.get_schema_info(schema_name)
        
        # Get last known schema state
        last_schema_query = """
        SELECT DISTINCT ON (object_name) 
            object_name, new_definition, detected_at
        FROM _graph_postgres_metadata.schema_change_log
        WHERE schema_name = %s
        ORDER BY object_name, detected_at DESC
        """
        last_changes = await self.connection.fetch_all(last_schema_query, (schema_name,))
        
        changes = []
        
        # Compare current schema with last known state
        # This is a simplified version - a full implementation would need
        # more sophisticated comparison
        for table_name, table_info in current_schema.items():
            # Check if table is new
            if not any(change["object_name"] == table_name for change in last_changes):
                change = SchemaChange(
                    change_type=ChangeType.CREATE,
                    object_type=ObjectType.TABLE,
                    schema_name=schema_name,
                    object_name=table_name,
                    parent_object=None,
                    old_definition=None,
                    new_definition=json.dumps({
                        "columns": table_info.columns,
                        "constraints": table_info.constraints,
                        "indexes": table_info.indexes
                    }),
                    change_details={"action": "table_created"}
                )
                changes.append(change)
                await self._record_schema_change(change)
        
        return changes
    
    async def _record_schema_change(self, change: SchemaChange) -> None:
        """Record a schema change in the metadata database."""
        insert_query = """
        INSERT INTO _graph_postgres_metadata.schema_change_log
        (change_type, object_type, schema_name, object_name, parent_object,
         old_definition, new_definition, change_details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        await self.connection.execute(
            insert_query,
            (
                change.change_type.value,
                change.object_type.value,
                change.schema_name,
                change.object_name,
                change.parent_object,
                change.old_definition,
                change.new_definition,
                json.dumps(change.change_details)
            )
        )
    
    async def apply_migration(self, migration_file: str, version: str, 
                            description: str | None = None) -> Migration:
        """Apply a database migration.
        
        Args:
            migration_file: Path to the migration SQL file
            version: Version identifier for the migration
            description: Optional description of the migration
            
        Returns:
            Migration object with execution details
        """
        async with self._migration_lock:
            # Check if migration already applied
            check_query = """
            SELECT * FROM _graph_postgres_metadata.migration_history
            WHERE migration_name = %s AND version = %s
            """
            existing = await self.connection.fetch_one(check_query, (migration_file, version))
            
            if existing and existing["status"] == MigrationStatus.COMPLETED.value:
                raise SchemaError(f"Migration {migration_file} version {version} already applied")
            
            # Read migration file
            try:
                with open(migration_file) as f:
                    migration_sql = f.read()
            except FileNotFoundError:
                raise SchemaError(f"Migration file not found: {migration_file}")
            
            # Calculate checksum
            checksum = hashlib.sha256(migration_sql.encode()).hexdigest()
            
            # Create migration record
            migration = Migration(
                migration_name=migration_file,
                version=version,
                description=description,
                status=MigrationStatus.RUNNING,
                checksum=checksum
            )
            
            # Record migration start
            start_time = datetime.now()
            insert_query = """
            INSERT INTO _graph_postgres_metadata.migration_history
            (migration_name, version, status, checksum)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """
            result = await self.connection.fetch_one(
                insert_query,
                (migration_file, version, MigrationStatus.RUNNING.value, checksum)
            )
            migration_id = result["id"]
            
            try:
                # Execute migration
                await self.connection.execute(migration_sql)
                
                # Update migration status
                end_time = datetime.now()
                execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
                
                update_query = """
                UPDATE _graph_postgres_metadata.migration_history
                SET status = %s, execution_time_ms = %s, executed_at = %s
                WHERE id = %s
                """
                await self.connection.execute(
                    update_query,
                    (MigrationStatus.COMPLETED.value, execution_time_ms, end_time, migration_id)
                )
                
                migration.status = MigrationStatus.COMPLETED
                migration.executed_at = end_time
                migration.execution_time_ms = execution_time_ms
                
                # Clear schema cache
                self._schema_cache.clear()
                
                return migration
                
            except Exception as e:
                # Record migration failure
                error_query = """
                UPDATE _graph_postgres_metadata.migration_history
                SET status = %s, error_message = %s
                WHERE id = %s
                """
                await self.connection.execute(
                    error_query,
                    (MigrationStatus.FAILED.value, str(e), migration_id)
                )
                
                migration.status = MigrationStatus.FAILED
                migration.error_message = str(e)
                
                raise SchemaError(f"Migration failed: {e}")
    
    def clear_cache(self) -> None:
        """Clear the schema cache."""
        self._schema_cache.clear()