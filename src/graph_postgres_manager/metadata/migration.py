"""Database migration functionality for PostgreSQL."""

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import SchemaError
from graph_postgres_manager.metadata.models import Migration, MigrationStatus


class MigrationManager:
    """Manages database migrations for PostgreSQL."""
    
    def __init__(self, connection: PostgresConnection, migrations_dir: str = "migrations"):
        """Initialize the migration manager.
        
        Args:
            connection: PostgreSQL connection instance
            migrations_dir: Directory containing migration files
        """
        self.connection = connection
        self.migrations_dir = Path(migrations_dir)
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """Initialize migration tracking tables."""
        init_query = """
        CREATE SCHEMA IF NOT EXISTS _graph_postgres_metadata;
        
        CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.migration_history (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) NOT NULL,
            version VARCHAR(50),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            execution_time_ms INTEGER,
            status VARCHAR(20) CHECK (
                status IN ('pending', 'running', 'completed', 'failed', 'rolled_back')
            ),
            error_message TEXT,
            checksum VARCHAR(64),
            rolled_back_at TIMESTAMP,
            CONSTRAINT unique_migration UNIQUE (migration_name, version)
        );
        """
        await self.connection.execute(init_query)
        
    async def get_pending_migrations(self) -> list[dict[str, Any]]:
        """Get list of pending migrations.
        
        Returns:
            List of pending migration files with their metadata
        """
        # Get all migration files
        migration_files = self._get_migration_files()
        
        # Get applied migrations
        applied_query = """
        SELECT migration_name, version, status
        FROM _graph_postgres_metadata.migration_history
        WHERE status IN ('completed', 'running')
        """
        applied_result = await self.connection.fetch_all(applied_query)
        applied_migrations = {
            (row["migration_name"], row["version"]): row["status"]
            for row in applied_result
        }
        
        # Find pending migrations
        pending = []
        for file_path in migration_files:
            migration_name = file_path.name
            version = self._extract_version(migration_name)
            
            if (migration_name, version) not in applied_migrations:
                with open(file_path) as f:
                    content = f.read()
                    checksum = hashlib.sha256(content.encode()).hexdigest()
                
                pending.append({
                    "file_path": str(file_path),
                    "migration_name": migration_name,
                    "version": version,
                    "checksum": checksum,
                    "size": file_path.stat().st_size
                })
                
        return sorted(pending, key=lambda x: x["version"])
    
    def _get_migration_files(self) -> list[Path]:
        """Get all migration files from the migrations directory."""
        if not self.migrations_dir.exists():
            return []
            
        # Look for SQL files with version prefix (e.g., 001_initial_schema.sql)
        migration_files = []
        for file_path in self.migrations_dir.glob("*.sql"):
            if self._is_valid_migration_file(file_path.name):
                migration_files.append(file_path)
                
        return sorted(migration_files)
    
    def _is_valid_migration_file(self, filename: str) -> bool:
        """Check if a filename follows migration naming convention."""
        # Expected format: XXX_description.sql where XXX is version number
        parts = filename.split("_", 1)
        if len(parts) >= 2 and parts[0].isdigit():
            return True
        return False
    
    def _extract_version(self, filename: str) -> str:
        """Extract version from migration filename."""
        parts = filename.split("_", 1)
        if parts and parts[0].isdigit():
            return parts[0].zfill(3)  # Pad with zeros for sorting
        return "000"
    
    async def apply_migration(self, file_path: str) -> Migration:
        """Apply a single migration file.
        
        Args:
            file_path: Path to the migration file
            
        Returns:
            Migration object with execution details
        """
        async with self._lock:
            file_path = Path(file_path)
            migration_name = file_path.name
            version = self._extract_version(migration_name)
            
            # Check if already applied
            check_query = """
            SELECT * FROM _graph_postgres_metadata.migration_history
            WHERE migration_name = %s AND version = %s
            AND status = 'completed'
            """
            existing = await self.connection.fetch_one(check_query, (migration_name, version))
            
            if existing:
                raise SchemaError(f"Migration {migration_name} already applied")
            
            # Read migration content
            with open(file_path) as f:
                migration_sql = f.read()
                
            checksum = hashlib.sha256(migration_sql.encode()).hexdigest()
            
            # Start migration
            start_time = datetime.now()
            insert_query = """
            INSERT INTO _graph_postgres_metadata.migration_history
            (migration_name, version, status, checksum)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (migration_name, version) DO UPDATE
            SET status = %s, checksum = %s
            RETURNING id
            """
            
            result = await self.connection.fetch_one(
                insert_query,
                (migration_name, version, MigrationStatus.RUNNING.value, checksum,
                 MigrationStatus.RUNNING.value, checksum)
            )
            migration_id = result["id"]
            
            try:
                # Execute migration
                await self.connection.execute(migration_sql)
                
                # Mark as completed
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
                
                return Migration(
                    migration_name=migration_name,
                    version=version,
                    status=MigrationStatus.COMPLETED,
                    executed_at=end_time,
                    execution_time_ms=execution_time_ms,
                    checksum=checksum
                )
                
            except Exception as e:
                # Mark as failed
                error_query = """
                UPDATE _graph_postgres_metadata.migration_history
                SET status = %s, error_message = %s
                WHERE id = %s
                """
                await self.connection.execute(
                    error_query,
                    (MigrationStatus.FAILED.value, str(e), migration_id)
                )
                raise SchemaError(f"Migration {migration_name} failed: {e}") from e
    
    async def apply_all_pending(self) -> list[Migration]:
        """Apply all pending migrations in order.
        
        Returns:
            List of applied migrations
        """
        pending = await self.get_pending_migrations()
        applied = []
        
        for migration_info in pending:
            try:
                migration = await self.apply_migration(migration_info["file_path"])
                applied.append(migration)
            except SchemaError as e:
                # Stop on first failure
                raise SchemaError(f"Migration failed, stopping: {e}")
                
        return applied
    
    async def rollback_migration(self, migration_name: str, version: str) -> None:
        """Rollback a migration (if rollback script exists).
        
        Args:
            migration_name: Name of the migration to rollback
            version: Version of the migration
        """
        # Look for rollback file (e.g., 001_initial_schema.down.sql)
        base_name = migration_name.replace(".sql", "")
        rollback_file = self.migrations_dir / f"{base_name}.down.sql"
        
        if not rollback_file.exists():
            raise SchemaError(f"No rollback script found for {migration_name}")
            
        # Check migration status
        status_query = """
        SELECT * FROM _graph_postgres_metadata.migration_history
        WHERE migration_name = %s AND version = %s
        AND status = 'completed'
        """
        migration = await self.connection.fetch_one(status_query, (migration_name, version))
        
        if not migration:
            raise SchemaError(f"Migration {migration_name} not found or not completed")
            
        # Execute rollback
        with open(rollback_file) as f:
            rollback_sql = f.read()
            
        try:
            await self.connection.execute(rollback_sql)
            
            # Update migration status
            update_query = """
            UPDATE _graph_postgres_metadata.migration_history
            SET status = %s, rolled_back_at = %s
            WHERE migration_name = %s AND version = %s
            """
            await self.connection.execute(
                update_query,
                (MigrationStatus.ROLLED_BACK.value, datetime.now(), migration_name, version)
            )
            
        except Exception as e:
            raise SchemaError(f"Rollback failed for {migration_name}: {e}")
    
    async def get_migration_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get migration history.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of migration history records
        """
        query = """
        SELECT 
            id,
            migration_name,
            version,
            status,
            executed_at,
            execution_time_ms,
            error_message,
            checksum,
            rolled_back_at
        FROM _graph_postgres_metadata.migration_history
        ORDER BY version DESC, executed_at DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        result = await self.connection.fetch_all(query)
        return [dict(row) for row in result]
    
    async def verify_migrations(self) -> dict[str, Any]:
        """Verify integrity of applied migrations.
        
        Returns:
            Dictionary with verification results
        """
        results = {
            "valid": [],
            "modified": [],
            "missing": [],
            "errors": []
        }
        
        # Get all completed migrations
        completed_query = """
        SELECT migration_name, version, checksum
        FROM _graph_postgres_metadata.migration_history
        WHERE status = 'completed'
        """
        completed = await self.connection.fetch_all(completed_query)
        
        for migration in completed:
            file_path = self.migrations_dir / migration["migration_name"]
            
            if not file_path.exists():
                results["missing"].append({
                    "migration_name": migration["migration_name"],
                    "version": migration["version"]
                })
                continue
                
            # Verify checksum
            try:
                with open(file_path) as f:
                    content = f.read()
                    current_checksum = hashlib.sha256(content.encode()).hexdigest()
                    
                if current_checksum != migration["checksum"]:
                    results["modified"].append({
                        "migration_name": migration["migration_name"],
                        "version": migration["version"],
                        "expected_checksum": migration["checksum"],
                        "actual_checksum": current_checksum
                    })
                else:
                    results["valid"].append({
                        "migration_name": migration["migration_name"],
                        "version": migration["version"]
                    })
                    
            except Exception as e:
                results["errors"].append({
                    "migration_name": migration["migration_name"],
                    "error": str(e)
                })
                
        return results
    
    def create_migration_template(self, name: str) -> str:
        """Create a new migration file template.
        
        Args:
            name: Description for the migration
            
        Returns:
            Path to the created migration file
        """
        # Get next version number
        existing_files = self._get_migration_files()
        if existing_files:
            last_version = self._extract_version(existing_files[-1].name)
            next_version = str(int(last_version) + 1).zfill(3)
        else:
            next_version = "001"
            
        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{next_version}_{name}_{timestamp}.sql"
        file_path = self.migrations_dir / filename
        
        # Create migrations directory if it doesn't exist
        self.migrations_dir.mkdir(exist_ok=True)
        
        # Create template content
        template = f"""-- Migration: {filename}
-- Created: {datetime.now().isoformat()}
-- Description: {name}

-- Add your migration SQL here

-- Example:
-- CREATE TABLE IF NOT EXISTS example_table (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );
"""
        
        # Write template
        with open(file_path, "w") as f:
            f.write(template)
            
        # Create rollback template
        rollback_path = self.migrations_dir / f"{next_version}_{name}_{timestamp}.down.sql"
        rollback_template = f"""-- Rollback for: {filename}
-- Created: {datetime.now().isoformat()}

-- Add your rollback SQL here

-- Example:
-- DROP TABLE IF EXISTS example_table;
"""
        
        with open(rollback_path, "w") as f:
            f.write(rollback_template)
            
        return str(file_path)