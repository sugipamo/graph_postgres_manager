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
RETURNS TABLE(status TEXT, check_time TIMESTAMP) AS $$
BEGIN
    RETURN QUERY SELECT 'healthy'::TEXT, NOW();
END;
$$ LANGUAGE plpgsql;

-- Create intent_ast_map table for intent-AST relationships
CREATE TABLE IF NOT EXISTS graph_data.intent_ast_map (
    id SERIAL PRIMARY KEY,
    intent_id VARCHAR(255) NOT NULL,
    ast_node_id VARCHAR(255) NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(intent_id, ast_node_id)
);

-- Create indexes for intent_ast_map
CREATE INDEX IF NOT EXISTS idx_intent_ast_map_intent_id ON graph_data.intent_ast_map(intent_id);
CREATE INDEX IF NOT EXISTS idx_intent_ast_map_ast_node_id ON graph_data.intent_ast_map(ast_node_id);
CREATE INDEX IF NOT EXISTS idx_intent_ast_map_confidence ON graph_data.intent_ast_map(confidence);

-- Create intent_vectors table for storing intent embeddings
CREATE TABLE IF NOT EXISTS graph_data.intent_vectors (
    id SERIAL PRIMARY KEY,
    intent_id VARCHAR(255) UNIQUE NOT NULL,
    vector_data TEXT NOT NULL,  -- JSON encoded vector
    dimensions INT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for intent_vectors
CREATE INDEX IF NOT EXISTS idx_intent_vectors_intent_id ON graph_data.intent_vectors(intent_id);

-- Create search_index table for full-text search
CREATE TABLE IF NOT EXISTS graph_data.search_index (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for search_index
CREATE INDEX IF NOT EXISTS idx_search_index_source_id ON graph_data.search_index(source_id);
CREATE INDEX IF NOT EXISTS idx_search_index_content ON graph_data.search_index USING GIN(to_tsvector('english', content));

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA graph_data TO testuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA graph_data TO testuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA graph_data TO testuser;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA graph_data TO testuser;