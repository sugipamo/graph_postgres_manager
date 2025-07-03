-- Create metadata schema for graph_postgres_manager
CREATE SCHEMA IF NOT EXISTS _graph_postgres_metadata;

-- Schema versions table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.schema_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64)
);

-- Migration history table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.migration_history (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL,
    version VARCHAR(50),
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INTEGER,
    status VARCHAR(20) CHECK (status IN ('pending', 'running', 'completed', 'failed', 'rolled_back')),
    error_message TEXT,
    checksum VARCHAR(64),
    rolled_back_at TIMESTAMP,
    CONSTRAINT unique_migration UNIQUE (migration_name, version)
);

-- Index statistics table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.index_stats (
    id SERIAL PRIMARY KEY,
    schema_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    index_name VARCHAR(255) NOT NULL,
    index_size BIGINT,
    index_scans BIGINT,
    index_tup_read BIGINT,
    index_tup_fetch BIGINT,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_unique BOOLEAN,
    is_primary BOOLEAN,
    is_partial BOOLEAN,
    index_definition TEXT,
    CONSTRAINT unique_index_stats UNIQUE (schema_name, table_name, index_name)
);

-- Query patterns table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.query_patterns (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    query_template TEXT NOT NULL,
    execution_count BIGINT DEFAULT 1,
    total_execution_time_ms BIGINT DEFAULT 0,
    avg_execution_time_ms FLOAT DEFAULT 0,
    min_execution_time_ms BIGINT,
    max_execution_time_ms BIGINT,
    last_executed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_query_pattern UNIQUE (query_hash)
);

-- Table statistics table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.table_stats (
    id SERIAL PRIMARY KEY,
    schema_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    row_count BIGINT,
    total_size BIGINT,
    table_size BIGINT,
    indexes_size BIGINT,
    toast_size BIGINT,
    last_vacuum TIMESTAMP,
    last_autovacuum TIMESTAMP,
    last_analyze TIMESTAMP,
    last_autoanalyze TIMESTAMP,
    dead_tuple_count BIGINT,
    live_tuple_count BIGINT,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_table_stats UNIQUE (schema_name, table_name, collected_at)
);

-- Schema change log table
CREATE TABLE IF NOT EXISTS _graph_postgres_metadata.schema_change_log (
    id SERIAL PRIMARY KEY,
    change_type VARCHAR(50) NOT NULL CHECK (change_type IN ('CREATE', 'ALTER', 'DROP', 'RENAME')),
    object_type VARCHAR(50) NOT NULL CHECK (object_type IN ('TABLE', 'COLUMN', 'INDEX', 'CONSTRAINT', 'SEQUENCE', 'VIEW', 'FUNCTION', 'TRIGGER')),
    schema_name VARCHAR(255),
    object_name VARCHAR(255) NOT NULL,
    parent_object VARCHAR(255),
    old_definition TEXT,
    new_definition TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_details JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_migration_history_status ON _graph_postgres_metadata.migration_history(status);
CREATE INDEX IF NOT EXISTS idx_migration_history_version ON _graph_postgres_metadata.migration_history(version);
CREATE INDEX IF NOT EXISTS idx_index_stats_usage ON _graph_postgres_metadata.index_stats(schema_name, table_name, index_scans);
CREATE INDEX IF NOT EXISTS idx_query_patterns_hash ON _graph_postgres_metadata.query_patterns(query_hash);
CREATE INDEX IF NOT EXISTS idx_query_patterns_count ON _graph_postgres_metadata.query_patterns(execution_count DESC);
CREATE INDEX IF NOT EXISTS idx_table_stats_timestamp ON _graph_postgres_metadata.table_stats(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_schema_change_timestamp ON _graph_postgres_metadata.schema_change_log(detected_at DESC);

-- Create update timestamp trigger function
CREATE OR REPLACE FUNCTION _graph_postgres_metadata.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update timestamp triggers
DROP TRIGGER IF EXISTS update_index_stats_timestamp ON _graph_postgres_metadata.index_stats;
CREATE TRIGGER update_index_stats_timestamp
    BEFORE UPDATE ON _graph_postgres_metadata.index_stats
    FOR EACH ROW
    EXECUTE FUNCTION _graph_postgres_metadata.update_updated_at();

DROP TRIGGER IF EXISTS update_query_patterns_timestamp ON _graph_postgres_metadata.query_patterns;
CREATE TRIGGER update_query_patterns_timestamp
    BEFORE UPDATE ON _graph_postgres_metadata.query_patterns
    FOR EACH ROW
    EXECUTE FUNCTION _graph_postgres_metadata.update_updated_at();

-- Grant permissions (adjust as needed)
GRANT USAGE ON SCHEMA _graph_postgres_metadata TO PUBLIC;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA _graph_postgres_metadata TO PUBLIC;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA _graph_postgres_metadata TO PUBLIC;