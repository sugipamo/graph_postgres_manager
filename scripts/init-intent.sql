-- Intent management tables for graph_postgres_manager

-- Enable pgvector extension if available
CREATE EXTENSION IF NOT EXISTS vector;

-- Create intent_ast_map table
CREATE TABLE IF NOT EXISTS intent_ast_map (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_id VARCHAR(255) NOT NULL,
    ast_node_id VARCHAR(255) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(intent_id, ast_node_id)
);

-- Create indexes for intent_ast_map
CREATE INDEX IF NOT EXISTS idx_intent_ast_intent_id ON intent_ast_map(intent_id);
CREATE INDEX IF NOT EXISTS idx_intent_ast_node_id ON intent_ast_map(ast_node_id);
CREATE INDEX IF NOT EXISTS idx_intent_ast_source_id ON intent_ast_map(source_id);
CREATE INDEX IF NOT EXISTS idx_intent_ast_confidence ON intent_ast_map(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_intent_ast_metadata ON intent_ast_map USING gin(metadata);

-- Create intent_vectors table (requires pgvector)
CREATE TABLE IF NOT EXISTS intent_vectors (
    intent_id VARCHAR(255) PRIMARY KEY,
    vector vector(768) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_intent_vectors_vector 
ON intent_vectors USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

-- Create metadata index
CREATE INDEX IF NOT EXISTS idx_intent_vectors_metadata ON intent_vectors USING gin(metadata);

-- Create update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_intent_ast_map_updated_at 
BEFORE UPDATE ON intent_ast_map
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust user as needed)
GRANT ALL PRIVILEGES ON TABLE intent_ast_map TO testuser;
GRANT ALL PRIVILEGES ON TABLE intent_vectors TO testuser;