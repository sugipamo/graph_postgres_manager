"""Data models for PostgreSQL metadata management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ChangeType(str, Enum):
    """Types of schema changes."""
    CREATE = "CREATE"
    ALTER = "ALTER"
    DROP = "DROP"
    RENAME = "RENAME"


class ObjectType(str, Enum):
    """Types of database objects."""
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    INDEX = "INDEX"
    CONSTRAINT = "CONSTRAINT"
    SEQUENCE = "SEQUENCE"
    VIEW = "VIEW"
    FUNCTION = "FUNCTION"
    TRIGGER = "TRIGGER"


class MigrationStatus(str, Enum):
    """Status of a migration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class TableInfo:
    """Information about a database table."""
    schema_name: str
    table_name: str
    columns: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    foreign_keys: list[dict[str, Any]]
    row_count: int | None = None
    size_bytes: int | None = None
    last_analyzed: datetime | None = None


@dataclass
class ColumnInfo:
    """Information about a table column."""
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: str | None = None
    character_maximum_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_reference: str | None = None


@dataclass
class IndexInfo:
    """Information about a database index."""
    schema_name: str
    table_name: str
    index_name: str
    is_unique: bool
    is_primary: bool
    is_partial: bool
    index_definition: str
    columns: list[str]
    size_bytes: int | None = None
    index_scans: int | None = None
    last_used: datetime | None = None


@dataclass
class TableStats:
    """Statistics for a database table."""
    schema_name: str
    table_name: str
    row_count: int
    total_size: int
    table_size: int
    indexes_size: int
    toast_size: int
    dead_tuple_count: int
    live_tuple_count: int
    last_vacuum: datetime | None = None
    last_autovacuum: datetime | None = None
    last_analyze: datetime | None = None
    last_autoanalyze: datetime | None = None
    collected_at: datetime = field(default_factory=datetime.now)


@dataclass
class QueryPattern:
    """Pattern of executed queries."""
    query_hash: str
    query_template: str
    execution_count: int
    total_execution_time_ms: int
    avg_execution_time_ms: float
    min_execution_time_ms: int
    max_execution_time_ms: int
    last_executed: datetime
    tables_referenced: list[str] = field(default_factory=list)


@dataclass
class SchemaChange:
    """Record of a schema change."""
    change_type: ChangeType
    object_type: ObjectType
    schema_name: str | None
    object_name: str
    parent_object: str | None
    old_definition: str | None
    new_definition: str | None
    change_details: dict[str, Any]
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class Migration:
    """Database migration information."""
    migration_name: str
    version: str
    description: str | None = None
    status: MigrationStatus = MigrationStatus.PENDING
    executed_at: datetime | None = None
    execution_time_ms: int | None = None
    error_message: str | None = None
    checksum: str | None = None
    rolled_back_at: datetime | None = None