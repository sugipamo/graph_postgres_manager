"""Data models for PostgreSQL metadata management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum


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
    columns: List[Dict[str, Any]]
    constraints: List[Dict[str, Any]]
    indexes: List[Dict[str, Any]]
    foreign_keys: List[Dict[str, Any]]
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    last_analyzed: Optional[datetime] = None


@dataclass
class ColumnInfo:
    """Information about a table column."""
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_reference: Optional[str] = None


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
    columns: List[str]
    size_bytes: Optional[int] = None
    index_scans: Optional[int] = None
    last_used: Optional[datetime] = None


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
    last_vacuum: Optional[datetime] = None
    last_autovacuum: Optional[datetime] = None
    last_analyze: Optional[datetime] = None
    last_autoanalyze: Optional[datetime] = None
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
    tables_referenced: List[str] = field(default_factory=list)


@dataclass
class SchemaChange:
    """Record of a schema change."""
    change_type: ChangeType
    object_type: ObjectType
    schema_name: Optional[str]
    object_name: str
    parent_object: Optional[str]
    old_definition: Optional[str]
    new_definition: Optional[str]
    change_details: Dict[str, Any]
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class Migration:
    """Database migration information."""
    migration_name: str
    version: str
    description: Optional[str] = None
    status: MigrationStatus = MigrationStatus.PENDING
    executed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    checksum: Optional[str] = None
    rolled_back_at: Optional[datetime] = None