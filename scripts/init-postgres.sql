-- Initial PostgreSQL setup for graph_postgres_manager

-- Create schema if needed
CREATE SCHEMA IF NOT EXISTS graph_data;

-- Create test tables
CREATE TABLE IF NOT EXISTS graph_data.metadata (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_metadata_key ON graph_data.metadata(key);

-- Create a test function for health checks
CREATE OR REPLACE FUNCTION graph_data.health_check()
RETURNS TABLE(status TEXT, timestamp TIMESTAMP) AS $$
BEGIN
    RETURN QUERY SELECT 'healthy'::TEXT, NOW();
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA graph_data TO testuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA graph_data TO testuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA graph_data TO testuser;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA graph_data TO testuser;