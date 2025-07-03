"""Index management functionality for PostgreSQL."""

import logging
from datetime import datetime
from typing import Any

from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.metadata.models import IndexInfo

logger = logging.getLogger(__name__)


class IndexManager:
    """Manages PostgreSQL indexes and provides optimization recommendations."""
    
    def __init__(self, connection: PostgresConnection):
        """Initialize the index manager.
        
        Args:
            connection: PostgreSQL connection instance
        """
        self.connection = connection
        self._index_cache: dict[str, list[IndexInfo]] = {}
        self._usage_stats_cache: dict[str, dict[str, Any]] = {}
        
    async def get_index_info(self, schema_name: str = "public", 
                           table_name: str | None = None) -> list[IndexInfo]:
        """Get information about indexes.
        
        Args:
            schema_name: Schema to inspect
            table_name: Optional specific table name
            
        Returns:
            List of IndexInfo objects
        """
        cache_key = f"{schema_name}.{table_name or '*'}"
        if cache_key in self._index_cache:
            return self._index_cache[cache_key]
        
        query = """
        SELECT 
            n.nspname as schema_name,
            t.relname as table_name,
            i.relname as index_name,
            idx.indisunique as is_unique,
            idx.indisprimary as is_primary,
            idx.indisvalid as is_valid,
            idx.indisready as is_ready,
            idx.indislive as is_live,
            idx.indisreplident as is_replica_identity,
            array_agg(a.attname ORDER BY array_position(idx.indkey, a.attnum)) as columns,
            pg_get_indexdef(idx.indexrelid) as index_definition,
            pg_relation_size(idx.indexrelid) as size_bytes,
            COALESCE(s.idx_scan, 0) as index_scans,
            COALESCE(s.idx_tup_read, 0) as tuples_read,
            COALESCE(s.idx_tup_fetch, 0) as tuples_fetched
        FROM pg_index idx
        JOIN pg_class i ON i.oid = idx.indexrelid
        JOIN pg_class t ON t.oid = idx.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(idx.indkey)
        LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = idx.indexrelid
        WHERE n.nspname = %s
        """
        
        params = [schema_name]
        if table_name:
            query += " AND t.relname = %s"
            params.append(table_name)
            
        query += """
        GROUP BY n.nspname, t.relname, i.relname, idx.indisunique, idx.indisprimary,
                 idx.indisvalid, idx.indisready, idx.indislive, idx.indisreplident,
                 idx.indexrelid, s.idx_scan, s.idx_tup_read, s.idx_tup_fetch
        ORDER BY n.nspname, t.relname, i.relname
        """
        
        result = await self.connection.fetch_all(query, tuple(params))
        
        indexes = []
        for row in result:
            # Check if index is partial
            is_partial = "WHERE" in row["index_definition"]
            
            index_info = IndexInfo(
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                index_name=row["index_name"],
                is_unique=row["is_unique"],
                is_primary=row["is_primary"],
                is_partial=is_partial,
                index_definition=row["index_definition"],
                columns=row["columns"],
                size_bytes=row["size_bytes"],
                index_scans=row["index_scans"]
            )
            indexes.append(index_info)
        
        self._index_cache[cache_key] = indexes
        return indexes
    
    async def analyze_index_usage(self, schema_name: str = "public", 
                                _days_back: int = 30) -> dict[str, Any]:
        """Analyze index usage patterns.
        
        Args:
            schema_name: Schema to analyze
            days_back: Number of days to look back for usage stats
            
        Returns:
            Dictionary with analysis results including unused indexes,
            duplicate indexes, and optimization recommendations
        """
        indexes = await self.get_index_info(schema_name)
        
        # Get table scan statistics
        table_stats = await self._get_table_scan_stats(schema_name)
        
        analysis = {
            "unused_indexes": [],
            "rarely_used_indexes": [],
            "duplicate_indexes": [],
            "missing_indexes": [],
            "large_unused_indexes": [],
            "index_bloat": [],
            "recommendations": []
        }
        
        # Analyze each index
        for index in indexes:
            # Skip primary keys
            if index.is_primary:
                continue
                
            # Check for unused indexes
            if index.index_scans == 0:
                analysis["unused_indexes"].append({
                    "index_name": index.index_name,
                    "table_name": index.table_name,
                    "size_bytes": index.size_bytes,
                    "columns": index.columns
                })
                
                # Flag large unused indexes
                if index.size_bytes and index.size_bytes > 10 * 1024 * 1024:  # 10MB
                    analysis["large_unused_indexes"].append({
                        "index_name": index.index_name,
                        "table_name": index.table_name,
                        "size_mb": index.size_bytes / (1024 * 1024)
                    })
            
            # Check for rarely used indexes
            elif index.index_scans and index.index_scans < 100:
                analysis["rarely_used_indexes"].append({
                    "index_name": index.index_name,
                    "table_name": index.table_name,
                    "scan_count": index.index_scans,
                    "size_bytes": index.size_bytes
                })
        
        # Find duplicate indexes
        duplicates = self._find_duplicate_indexes(indexes)
        analysis["duplicate_indexes"] = duplicates
        
        # Check for missing indexes based on table scans
        missing = await self._suggest_missing_indexes(schema_name, table_stats)
        analysis["missing_indexes"] = missing
        
        # Check index bloat
        bloat = await self._check_index_bloat(schema_name)
        analysis["index_bloat"] = bloat
        
        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        # Cache the analysis
        self._usage_stats_cache[schema_name] = analysis
        
        return analysis
    
    async def _get_table_scan_stats(self, schema_name: str) -> dict[str, Any]:
        """Get table scan statistics."""
        query = """
        SELECT 
            schemaname,
            tablename,
            seq_scan,
            seq_tup_read,
            idx_scan,
            idx_tup_fetch,
            n_tup_ins,
            n_tup_upd,
            n_tup_del,
            n_live_tup,
            n_dead_tup,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = %s
        AND seq_scan > 0
        ORDER BY seq_tup_read DESC
        """
        
        result = await self.connection.fetch_all(query, (schema_name,))
        
        stats = {}
        for row in result:
            stats[row["tablename"]] = dict(row)
            
        return stats
    
    def _find_duplicate_indexes(self, indexes: list[IndexInfo]) -> list[dict[str, Any]]:
        """Find duplicate or redundant indexes."""
        duplicates = []
        
        # Group indexes by table
        table_indexes: dict[str, list[IndexInfo]] = {}
        for index in indexes:
            key = f"{index.schema_name}.{index.table_name}"
            if key not in table_indexes:
                table_indexes[key] = []
            table_indexes[key].append(index)
        
        # Check each table for duplicates
        for table_key, idx_list in table_indexes.items():
            for i, idx1 in enumerate(idx_list):
                for idx2 in idx_list[i+1:]:
                    # Check if indexes have same columns
                    if set(idx1.columns) == set(idx2.columns):
                        duplicates.append({
                            "table": table_key,
                            "index1": idx1.index_name,
                            "index2": idx2.index_name,
                            "columns": idx1.columns,
                            "type": "exact_duplicate"
                        })
                    # Check if one index is a prefix of another
                    elif (len(idx1.columns) < len(idx2.columns) and 
                          idx1.columns == idx2.columns[:len(idx1.columns)]):
                        duplicates.append({
                            "table": table_key,
                            "redundant_index": idx1.index_name,
                            "covering_index": idx2.index_name,
                            "type": "redundant_prefix"
                        })
                        
        return duplicates
    
    async def _suggest_missing_indexes(self, schema_name: str, 
                                     table_stats: dict[str, Any]) -> list[dict[str, Any]]:
        """Suggest potentially missing indexes based on query patterns."""
        suggestions = []
        
        # Get slow queries from pg_stat_statements if available
        try:
            slow_queries = await self._get_slow_queries(schema_name)
            
            for query_info in slow_queries:
                # Simple heuristic: Look for WHERE clauses on columns without indexes
                suggestion = await self._analyze_query_for_indexes(query_info)
                if suggestion:
                    suggestions.append(suggestion)
                    
        except Exception:
            # pg_stat_statements might not be available
            logger.debug("pg_stat_statements not available, skipping query analysis")
        
        # Check tables with high sequential scan to index scan ratio
        for table_name, stats in table_stats.items():
            seq_scan = stats.get("seq_scan", 0)
            idx_scan = stats.get("idx_scan", 0)
            
            if seq_scan > 1000 and (idx_scan == 0 or seq_scan / idx_scan > 10):
                suggestions.append({
                    "table": f"{schema_name}.{table_name}",
                    "reason": "high_sequential_scan_ratio",
                    "seq_scans": seq_scan,
                    "index_scans": idx_scan,
                    "recommendation": f"Consider adding indexes to {table_name}"
                })
                
        return suggestions
    
    async def _get_slow_queries(self, _schema_name: str) -> list[dict[str, Any]]:
        """Get slow queries from pg_stat_statements."""
        query = """
        SELECT 
            query,
            calls,
            total_exec_time,
            mean_exec_time,
            rows
        FROM pg_stat_statements
        WHERE query NOT LIKE 'EXPLAIN%'
        AND query NOT LIKE '%pg_stat_statements%'
        AND mean_exec_time > 100  -- queries slower than 100ms
        ORDER BY mean_exec_time DESC
        LIMIT 50
        """
        
        try:
            result = await self.connection.fetch_all(query)
            return [dict(row) for row in result]
        except Exception:
            return []
    
    async def _analyze_query_for_indexes(
        self, _query_info: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Analyze a query to suggest indexes."""
        # This is a simplified implementation
        # A full implementation would parse the query and analyze the execution plan
        return None
    
    async def _check_index_bloat(self, schema_name: str) -> list[dict[str, Any]]:
        """Check for index bloat."""
        query = """
        WITH btree_index_atts AS (
            SELECT 
                nspname,
                indexclass.relname as index_name,
                indexclass.reltuples,
                indexclass.relpages,
                tableclass.relname as tablename,
                regexp_split_to_table(indkey::text, ' ')::smallint AS attnum,
                indexrelid as index_oid
            FROM pg_index
            JOIN pg_class as indexclass ON pg_index.indexrelid = indexclass.oid
            JOIN pg_class as tableclass ON pg_index.indrelid = tableclass.oid
            JOIN pg_namespace ON pg_namespace.oid = indexclass.relnamespace
            WHERE indexclass.relam = (SELECT oid FROM pg_am WHERE amname = 'btree')
            AND nspname = %s
        ),
        index_item_sizes AS (
            SELECT
                ind_atts.nspname,
                ind_atts.index_name,
                ind_atts.tablename,
                ind_atts.reltuples,
                ind_atts.relpages,
                ind_atts.index_oid,
                (SELECT SUM(stawidth) FROM pg_statistic 
                 WHERE starelid = ind_atts.index_oid) AS index_size
            FROM btree_index_atts AS ind_atts
            GROUP BY 1,2,3,4,5,6
        )
        SELECT
            index_name,
            tablename,
            pg_size_pretty(pg_relation_size(index_oid)) as index_size,
            CASE WHEN relpages > 0
                THEN ROUND(100.0 * (1.0 - (reltuples * index_size) / (relpages * 8192.0)), 2)
                ELSE 0
            END AS bloat_percentage
        FROM index_item_sizes
        WHERE relpages > 10  -- Only check indexes with more than 10 pages
        ORDER BY bloat_percentage DESC
        """
        
        result = await self.connection.fetch_all(query, (schema_name,))
        
        bloated_indexes = []
        for row in result:
            if row["bloat_percentage"] and row["bloat_percentage"] > 20:
                bloated_indexes.append({
                    "index_name": row["index_name"],
                    "table_name": row["tablename"],
                    "index_size": row["index_size"],
                    "bloat_percentage": row["bloat_percentage"]
                })
                
        return bloated_indexes
    
    async def suggest_indexes(self, schema_name: str = "public",
                            analyze_workload: bool = True) -> list[dict[str, Any]]:
        """Suggest new indexes based on workload analysis.
        
        Args:
            schema_name: Schema to analyze
            analyze_workload: Whether to analyze query workload
            
        Returns:
            List of index suggestions with CREATE INDEX statements
        """
        suggestions = []
        
        # Get current indexes
        current_indexes = await self.get_index_info(schema_name)
        
        # Get table statistics
        table_stats = await self._get_table_scan_stats(schema_name)
        
        # Analyze workload if requested
        if analyze_workload:
            workload_suggestions = await self._analyze_workload_patterns(schema_name)
            suggestions.extend(workload_suggestions)
        
        # Check for tables with frequent sequential scans
        for table_name, stats in table_stats.items():
            if stats["seq_scan"] > 1000:
                # Get frequently filtered columns
                filtered_columns = await self._get_frequently_filtered_columns(
                    schema_name, table_name
                )
                
                for column_info in filtered_columns:
                    # Check if index already exists
                    index_exists = any(
                        column_info["column"] in idx.columns
                        for idx in current_indexes
                        if idx.table_name == table_name
                    )
                    
                    if not index_exists:
                        suggestions.append({
                            "table": f"{schema_name}.{table_name}",
                            "column": column_info["column"],
                            "reason": "frequently_filtered_column",
                            "filter_count": column_info["filter_count"],
                            "create_statement": (
                                f"CREATE INDEX idx_{table_name}_{column_info['column']} "
                                f"ON {schema_name}.{table_name} ({column_info['column']})"
                            )
                        })
        
        # Sort suggestions by potential impact
        suggestions.sort(key=lambda x: x.get("filter_count", 0), reverse=True)
        
        return suggestions[:10]  # Return top 10 suggestions
    
    async def _analyze_workload_patterns(self, _schema_name: str) -> list[dict[str, Any]]:
        """Analyze query workload patterns for index suggestions."""
        # This would analyze pg_stat_statements or query logs
        # For now, return empty list as this requires more complex implementation
        return []
    
    async def _get_frequently_filtered_columns(self, _schema_name: str, 
                                             _table_name: str) -> list[dict[str, Any]]:
        """Get columns that are frequently used in WHERE clauses."""
        # This is a simplified implementation
        # A full implementation would analyze query patterns
        return []
    
    def _generate_recommendations(self, analysis: dict[str, Any]) -> list[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Recommend dropping unused indexes
        if analysis["unused_indexes"]:
            total_size = sum(idx["size_bytes"] for idx in analysis["unused_indexes"] 
                           if idx["size_bytes"])
            recommendations.append(
                f"Consider dropping {len(analysis['unused_indexes'])} unused indexes "
                f"to save {total_size / (1024*1024):.1f} MB of storage"
            )
        
        # Recommend removing duplicate indexes
        if analysis["duplicate_indexes"]:
            recommendations.append(
                f"Found {len(analysis['duplicate_indexes'])} duplicate or redundant indexes "
                "that can be consolidated"
            )
        
        # Recommend rebuilding bloated indexes
        if analysis["index_bloat"]:
            for bloated in analysis["index_bloat"]:
                if bloated["bloat_percentage"] > 50:
                    recommendations.append(
                        f"Index {bloated['index_name']} is {bloated['bloat_percentage']:.1f}% "
                        "bloated and should be rebuilt with REINDEX"
                    )
        
        # Recommend adding missing indexes
        if analysis["missing_indexes"]:
            recommendations.append(
                f"Consider adding indexes on {len(analysis['missing_indexes'])} tables "
                "with high sequential scan rates"
            )
        
        return recommendations
    
    async def create_index(self, schema_name: str, table_name: str, 
                         columns: list[str], index_name: str | None = None,
                         unique: bool = False, concurrent: bool = True) -> str:
        """Create a new index.
        
        Args:
            schema_name: Schema containing the table
            table_name: Table to index
            columns: List of columns to include in the index
            index_name: Optional index name (auto-generated if not provided)
            unique: Whether to create a unique index
            concurrent: Whether to create index concurrently
            
        Returns:
            Name of the created index
        """
        if not index_name:
            # Generate index name
            column_str = "_".join(columns)
            index_name = f"idx_{table_name}_{column_str}"[:63]  # PostgreSQL identifier limit
        
        # Build CREATE INDEX statement
        create_stmt = "CREATE "
        if unique:
            create_stmt += "UNIQUE "
        create_stmt += "INDEX "
        if concurrent:
            create_stmt += "CONCURRENTLY "
        
        create_stmt += f"{index_name} ON {schema_name}.{table_name} ("
        create_stmt += ", ".join(columns)
        create_stmt += ")"
        
        # Execute the statement
        await self.connection.execute(create_stmt)
        
        # Clear cache
        self._index_cache.clear()
        
        # Record index creation in metadata
        await self._record_index_creation(schema_name, table_name, index_name, columns)
        
        return index_name
    
    async def _record_index_creation(self, schema_name: str, table_name: str,
                                   index_name: str, columns: list[str]) -> None:
        """Record index creation in metadata."""
        insert_query = """
        INSERT INTO _graph_postgres_metadata.index_stats
        (schema_name, table_name, index_name, is_unique, is_primary, 
         is_partial, index_definition, created_at)
        VALUES (%s, %s, %s, false, false, false, %s, %s)
        ON CONFLICT (schema_name, table_name, index_name) DO UPDATE
        SET updated_at = %s
        """
        
        definition = (
            f"CREATE INDEX {index_name} ON {schema_name}.{table_name} "
            f"({', '.join(columns)})"
        )
        now = datetime.now()
        
        await self.connection.execute(
            insert_query,
            (schema_name, table_name, index_name, definition, now, now)
        )
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._index_cache.clear()
        self._usage_stats_cache.clear()