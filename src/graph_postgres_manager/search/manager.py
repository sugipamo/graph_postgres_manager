"""SearchManager implementation for unified search functionality."""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from graph_postgres_manager.connections.neo4j import Neo4jConnection
from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import DataOperationError
from graph_postgres_manager.intent.manager import IntentManager
from graph_postgres_manager.search.models import SearchQuery, SearchResult, SearchType

logger = logging.getLogger(__name__)


class SearchManager:
    """Manages unified search across Neo4j graph, PostgreSQL text, and vector embeddings."""
    
    def __init__(
        self,
        neo4j_connection: Neo4jConnection,
        postgres_connection: PostgresConnection,
        intent_manager: IntentManager
    ):
        self.neo4j = neo4j_connection
        self.postgres = postgres_connection
        self.intent_manager = intent_manager
        self._search_cache: dict[str, list[SearchResult]] = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Execute a search query across all configured search types.
        
        Args:
            query: Search query parameters
            
        Returns:
            List of search results ranked by relevance
        """
        if SearchType.UNIFIED in query.search_types:
            return await self._unified_search(query)
        
        # Execute individual search types
        tasks = []
        if SearchType.GRAPH in query.search_types:
            tasks.append(self._graph_search(query))
        if SearchType.VECTOR in query.search_types:
            tasks.append(self._vector_search(query))
        if SearchType.TEXT in query.search_types:
            tasks.append(self._text_search(query))
        
        if not tasks:
            return []
        
        # Execute searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("Search error: %s", result)
                continue
            all_results.extend(result)
        
        return self._rank_results(all_results, query)
    
    async def _unified_search(self, query: SearchQuery) -> list[SearchResult]:
        """Execute unified search across all types."""
        # Execute all search types in parallel
        graph_task = self._graph_search(query)
        vector_task = self._vector_search(query) if query.vector else None
        text_task = self._text_search(query)
        
        tasks = [graph_task, text_task]
        if vector_task:
            tasks.append(vector_task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        graph_results = results[0] if not isinstance(results[0], Exception) else []
        text_results = results[1] if not isinstance(results[1], Exception) else []
        vector_results = (
            results[2] if len(results) > 2 and not isinstance(results[2], Exception) 
            else []
        )
        
        # Combine and rank
        all_results = []
        all_results.extend(graph_results)
        all_results.extend(text_results)
        all_results.extend(vector_results)
        
        return self._rank_results(all_results, query)
    
    async def _graph_search(self, query: SearchQuery) -> list[SearchResult]:
        """Search Neo4j graph database."""
        try:
            # Build Cypher query based on filters
            cypher = self._build_graph_query(query)
            params = {"search_query": query.query.lower()}
            
            results = await self.neo4j.execute_query(cypher, params)
            
            return [
                SearchResult(
                    id=str(r["id"]),
                    source_id=r.get("source_id", ""),
                    node_type=r.get("node_type"),
                    content=r.get("value", ""),
                    score=self._calculate_graph_score(r, query),
                    search_type=SearchType.GRAPH,
                    metadata=r.get("metadata", {}),
                    file_path=r.get("file_path"),
                    line_number=r.get("lineno")
                )
                for r in results
            ]
        except Exception as e:
            logger.error("Graph search error: %s", e)
            raise DataOperationError(f"Graph search failed: {e}") from e
    
    async def _vector_search(self, query: SearchQuery) -> list[SearchResult]:
        """Search using vector embeddings."""
        if not query.vector:
            return []
            
        try:
            # Use intent manager for vector search
            results = await self.intent_manager.search_ast_by_intent_vector(
                query.vector,
                source_id=query.filters.source_ids[0] if query.filters.source_ids else None,
                similarity_threshold=query.filters.min_confidence,
                limit=query.filters.max_results
            )
            
            return [
                SearchResult(
                    id=r["mapping_id"],
                    source_id=r["source_id"],
                    content=f"AST Node: {r['ast_node_id']}",
                    score=r["similarity"],
                    search_type=SearchType.VECTOR,
                    metadata=r.get("metadata", {})
                )
                for r in results
            ]
        except Exception as e:
            logger.error("Vector search error: %s", e)
            raise DataOperationError(f"Vector search failed: {e}") from e
    
    async def _text_search(self, query: SearchQuery) -> list[SearchResult]:
        """Search PostgreSQL full-text index."""
        try:
            sql = self._build_text_query(query)
            params = [query.query]
            
            async with self.postgres.get_connection() as conn:
                rows = await conn.fetch(sql, *params)
                
            return [
                SearchResult(
                    id=str(row["id"]),
                    source_id=row.get("source_id", ""),
                    content=row.get("content", ""),
                    score=self._calculate_text_score(row, query),
                    search_type=SearchType.TEXT,
                    metadata=json.loads(row["metadata"]) if row.get("metadata") else {},
                    highlights=self._extract_highlights(row, query)
                )
                for row in rows
            ]
        except Exception as e:
            logger.error("Text search error: %s", e)
            raise DataOperationError(f"Text search failed: {e}") from e
    
    def _build_graph_query(self, query: SearchQuery) -> str:
        """Build Cypher query for graph search."""
        conditions = [
            "toLower(n.value) CONTAINS $search_query OR toLower(n.id) CONTAINS $search_query"
        ]
        
        if query.filters.node_types:
            types = ", ".join(f"'{t}'" for t in query.filters.node_types)
            conditions.append(f"n.node_type IN [{types}]")
        
        if query.filters.source_ids:
            sources = ", ".join(f"'{s}'" for s in query.filters.source_ids)
            conditions.append(f"n.source_id IN [{sources}]")
        
        where_clause = " AND ".join(conditions)
        
        return f"""
        MATCH (n)
        WHERE {where_clause}
        RETURN n.id as id, n.source_id as source_id, n.node_type as node_type,
               n.value as value, n.lineno as lineno, n.metadata as metadata,
               n.file_path as file_path
        LIMIT {query.filters.max_results}
        """
    
    def _build_text_query(self, query: SearchQuery) -> str:
        """Build SQL query for text search."""
        # Basic full-text search query
        sql = """
        SELECT id, source_id, content, metadata,
               ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) as rank
        FROM graph_data.search_index
        WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
        """
        
        conditions = []
        if query.filters.source_ids:
            sources = ", ".join(f"'{s}'" for s in query.filters.source_ids)
            conditions.append(f"source_id IN ({sources})")
        
        if conditions:
            sql += " AND " + " AND ".join(conditions)
        
        sql += f" ORDER BY rank DESC LIMIT {query.filters.max_results}"
        return sql
    
    def _rank_results(self, results: list[SearchResult], query: SearchQuery) -> list[SearchResult]:
        """Rank and combine search results."""
        if not results:
            return []
        
        # Group results by ID to handle duplicates
        grouped = defaultdict(list)
        for result in results:
            grouped[result.id].append(result)
        
        # Combine scores for duplicates
        final_results = []
        for result_id, group in grouped.items():
            if len(group) == 1:
                final_results.append(group[0])
            else:
                # Combine scores using weights
                combined = group[0]
                combined.score = sum(
                    r.score * query.weights.get(r.search_type, 0.33)
                    for r in group
                ) / len(group)
                combined.search_type = SearchType.UNIFIED
                final_results.append(combined)
        
        # Sort by score
        final_results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply result limit
        return final_results[:query.filters.max_results]
    
    def _calculate_graph_score(self, result: dict[str, Any], query: SearchQuery) -> float:
        """Calculate relevance score for graph search result."""
        score = 0.0
        query_lower = query.query.lower()
        
        # Exact match on ID or value
        if result.get("id", "").lower() == query_lower:
            score = 1.0
        elif result.get("value", "").lower() == query_lower:
            score = 0.9
        # Partial match
        elif query_lower in result.get("value", "").lower():
            score = 0.7
        elif query_lower in result.get("id", "").lower():
            score = 0.6
        else:
            score = 0.4
        
        # Boost score for specific node types if filtered
        if query.filters.node_types and result.get("node_type") in query.filters.node_types:
            score *= 1.2
        
        return min(1.0, score)
    
    def _calculate_text_score(self, result: dict[str, Any], _query: SearchQuery) -> float:
        """Calculate relevance score for text search result."""
        # PostgreSQL ts_rank provides a score, normalize it
        rank = result.get("rank", 0.0)
        # Typical ts_rank values are 0.0 to 1.0 but can exceed 1.0
        return min(1.0, rank)
    
    def _extract_highlights(self, result: dict[str, Any], query: SearchQuery) -> list[str]:
        """Extract highlighted snippets from text search results."""
        content = result.get("content", "")
        if not content:
            return []
        
        # Simple highlighting - find query terms in content
        highlights = []
        query_terms = query.query.lower().split()
        
        for term in query_terms:
            index = content.lower().find(term)
            if index != -1:
                start = max(0, index - 50)
                end = min(len(content), index + len(term) + 50)
                highlight = content[start:end]
                if start > 0:
                    highlight = "..." + highlight
                if end < len(content):
                    highlight = highlight + "..."
                highlights.append(highlight)
        
        return highlights[:3]  # Return up to 3 highlights
    
    def clear_cache(self) -> None:
        """Clear the search result cache."""
        self._search_cache.clear()
        logger.info("Search cache cleared")