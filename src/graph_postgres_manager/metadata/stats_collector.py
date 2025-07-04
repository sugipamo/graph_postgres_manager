"""Statistics collection functionality for PostgreSQL."""

import asyncio
import contextlib
import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from graph_postgres_manager.connections.postgres import PostgresConnection
from graph_postgres_manager.exceptions import MetadataError
from graph_postgres_manager.metadata.models import QueryPattern, TableStats


class StatsCollector:
    """Collects and analyzes PostgreSQL statistics."""
    
    def __init__(self, connection: PostgresConnection):
        """Initialize the stats collector.
        
        Args:
            connection: PostgreSQL connection instance
        """
        self.connection = connection
        self._stats_cache: dict[str, Any] = {}
        self._collection_interval = timedelta(hours=1)  # Default collection interval
        self._last_collection_time: datetime | None = None
        
    async def collect_table_stats(self, schema_name: str = "public",
                                table_name: str | None = None) -> list[TableStats]:
        """Collect statistics for tables.
        
        Args:
            schema_name: Schema to collect stats for
            table_name: Optional specific table name
            
        Returns:
            List of TableStats objects
        """
        query = """
        SELECT 
            n.nspname as schema_name,
            c.relname as table_name,
            pg_stat_get_live_tuples(c.oid) as live_tuple_count,
            pg_stat_get_dead_tuples(c.oid) as dead_tuple_count,
            COALESCE(pg_stat_get_numscans(c.oid), 0) as seq_scans,
            pg_total_relation_size(c.oid) as total_size,
            pg_relation_size(c.oid) as table_size,
            pg_indexes_size(c.oid) as indexes_size,
            COALESCE(pg_relation_size(c.oid, 'fsm'), 0) +
            COALESCE(pg_relation_size(c.oid, 'vm'), 0) as toast_size,
            s.last_vacuum,
            s.last_autovacuum,
            s.last_analyze,
            s.last_autoanalyze,
            s.n_tup_ins,
            s.n_tup_upd,
            s.n_tup_del,
            s.n_tup_hot_upd,
            s.vacuum_count,
            s.autovacuum_count,
            s.analyze_count,
            s.autoanalyze_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.schemaname = n.nspname AND s.tablename = c.relname
        WHERE c.relkind = 'r'
        AND n.nspname = %s
        """
        
        params = [schema_name]
        if table_name:
            query += " AND c.relname = %s"
            params.append(table_name)
            
        query += " ORDER BY pg_total_relation_size(c.oid) DESC"
        
        result = await self.connection.fetch_all(query, tuple(params))
        
        stats_list = []
        for row in result:
            # Calculate estimated row count
            live_tuples = row["live_tuple_count"] or 0
            dead_tuples = row["dead_tuple_count"] or 0
            row_count = live_tuples + dead_tuples
            
            stats = TableStats(
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                row_count=row_count,
                total_size=row["total_size"] or 0,
                table_size=row["table_size"] or 0,
                indexes_size=row["indexes_size"] or 0,
                toast_size=row["toast_size"] or 0,
                dead_tuple_count=dead_tuples,
                live_tuple_count=live_tuples,
                last_vacuum=row["last_vacuum"],
                last_autovacuum=row["last_autovacuum"],
                last_analyze=row["last_analyze"],
                last_autoanalyze=row["last_autoanalyze"]
            )
            stats_list.append(stats)
            
            # Store in metadata
            await self._store_table_stats(stats)
            
        return stats_list
    
    async def _store_table_stats(self, stats: TableStats) -> None:
        """Store table statistics in metadata database."""
        insert_query = """
        INSERT INTO _graph_postgres_metadata.table_stats
        (schema_name, table_name, row_count, total_size, table_size,
         indexes_size, toast_size, last_vacuum, last_autovacuum,
         last_analyze, last_autoanalyze, dead_tuple_count, live_tuple_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        await self.connection.execute(
            insert_query,
            (
                stats.schema_name, stats.table_name, stats.row_count,
                stats.total_size, stats.table_size, stats.indexes_size,
                stats.toast_size, stats.last_vacuum, stats.last_autovacuum,
                stats.last_analyze, stats.last_autoanalyze,
                stats.dead_tuple_count, stats.live_tuple_count
            )
        )
    
    async def analyze_query_patterns(self, min_execution_time_ms: float = 10.0,
                                   limit: int = 100) -> list[QueryPattern]:
        """Analyze query execution patterns.
        
        Args:
            min_execution_time_ms: Minimum execution time to consider
            limit: Maximum number of patterns to return
            
        Returns:
            List of QueryPattern objects
        """
        # Check if pg_stat_statements is available
        check_query = """
        SELECT EXISTS (
            SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
        )
        """
        result = await self.connection.fetch_one(check_query)
        
        if not result["exists"]:
            raise MetadataError("pg_stat_statements extension is not installed")
        
        # Get query patterns
        query = """
        SELECT 
            query,
            calls,
            total_exec_time as total_time_ms,
            mean_exec_time as mean_time_ms,
            min_exec_time as min_time_ms,
            max_exec_time as max_time_ms,
            stddev_exec_time as stddev_time_ms,
            rows,
            shared_blks_hit,
            shared_blks_read,
            temp_blks_read,
            temp_blks_written
        FROM pg_stat_statements
        WHERE mean_exec_time >= %s
        AND query NOT LIKE '%%pg_stat_statements%%'
        AND query NOT LIKE 'EXPLAIN%%'
        AND query NOT LIKE '%%_graph_postgres_metadata%%'
        ORDER BY total_exec_time DESC
        LIMIT %s
        """
        
        result = await self.connection.fetch_all(query, (min_execution_time_ms, limit))
        
        patterns = []
        for row in result:
            # Normalize query to create pattern
            normalized_query, query_hash = self._normalize_query(row["query"])
            
            # Extract table references
            tables = self._extract_table_references(row["query"])
            
            pattern = QueryPattern(
                query_hash=query_hash,
                query_template=normalized_query,
                execution_count=row["calls"],
                total_execution_time_ms=int(row["total_time_ms"]),
                avg_execution_time_ms=row["mean_time_ms"],
                min_execution_time_ms=int(row["min_time_ms"]),
                max_execution_time_ms=int(row["max_time_ms"]),
                last_executed=datetime.now(),  # Approximation
                tables_referenced=tables
            )
            patterns.append(pattern)
            
            # Store in metadata
            await self._store_query_pattern(pattern)
            
        return patterns
    
    def _normalize_query(self, query: str) -> tuple[str, str]:
        """Normalize a query to create a pattern template.
        
        Args:
            query: Raw SQL query
            
        Returns:
            Tuple of (normalized_query, query_hash)
        """
        # Remove extra whitespace
        normalized = " ".join(query.split())
        
        # Replace literal values with placeholders
        # Numbers
        normalized = re.sub(r"\b\d+\.?\d*\b", "?", normalized)
        # Single quoted strings
        normalized = re.sub(r"'[^']*'", "?", normalized)
        # Double quoted identifiers (leave as is)
        
        # Replace IN lists with single placeholder
        normalized = re.sub(r"IN\s*\([^)]+\)", "IN (?)", normalized)
        
        # Calculate hash
        query_hash = hashlib.sha256(normalized.encode()).hexdigest()
        
        return normalized, query_hash
    
    def _extract_table_references(self, query: str) -> list[str]:
        """Extract table references from a query.
        
        Args:
            query: SQL query
            
        Returns:
            List of table names referenced in the query
        """
        tables = []
        
        # Pattern for quoted identifiers
        quoted_pattern = r'"([^"]+)"'
        
        # Pattern for unquoted identifiers
        unquoted_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
        
        # Combined pattern: quoted or unquoted identifiers
        identifier_pattern = f"(?:{quoted_pattern}|{unquoted_pattern})"
        
        # FROM clause
        from_pattern = rf"FROM\s+(?:[\w\.]+\.)?{identifier_pattern}"
        matches = re.finditer(from_pattern, query, re.IGNORECASE)
        for m in matches:
            # Get the first non-None group (either quoted or unquoted)
            table = m.group(1) or m.group(2)
            if table:
                tables.append(table)
        
        # JOIN clauses
        join_pattern = rf"JOIN\s+(?:[\w\.]+\.)?{identifier_pattern}"
        matches = re.finditer(join_pattern, query, re.IGNORECASE)
        for m in matches:
            table = m.group(1) or m.group(2)
            if table:
                tables.append(table)
        
        # UPDATE/INSERT/DELETE
        update_pattern = (
            rf"(?:UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+"
            rf"(?:[\w\.]+\.)?{identifier_pattern}"
        )
        matches = re.finditer(update_pattern, query, re.IGNORECASE)
        for m in matches:
            table = m.group(1) or m.group(2)
            if table:
                tables.append(table)
        
        # Remove duplicates
        return list(set(tables))
    
    async def _store_query_pattern(self, pattern: QueryPattern) -> None:
        """Store or update query pattern in metadata database."""
        upsert_query = """
        INSERT INTO _graph_postgres_metadata.query_patterns
        (query_hash, query_template, execution_count, total_execution_time_ms,
         avg_execution_time_ms, min_execution_time_ms, max_execution_time_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (query_hash) DO UPDATE SET
            execution_count = query_patterns.execution_count + EXCLUDED.execution_count,
            total_execution_time_ms = (
                query_patterns.total_execution_time_ms + EXCLUDED.total_execution_time_ms
            ),
            avg_execution_time_ms = (
                (query_patterns.total_execution_time_ms + EXCLUDED.total_execution_time_ms) / 
                (query_patterns.execution_count + EXCLUDED.execution_count)
            ),
            min_execution_time_ms = LEAST(
                query_patterns.min_execution_time_ms, EXCLUDED.min_execution_time_ms
            ),
            max_execution_time_ms = GREATEST(
                query_patterns.max_execution_time_ms, EXCLUDED.max_execution_time_ms
            ),
            last_executed = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        """
        
        await self.connection.execute(
            upsert_query,
            (
                pattern.query_hash, pattern.query_template,
                pattern.execution_count, pattern.total_execution_time_ms,
                pattern.avg_execution_time_ms, pattern.min_execution_time_ms,
                pattern.max_execution_time_ms
            )
        )
    
    async def generate_report(self, schema_name: str = "public",
                            include_queries: bool = True) -> dict[str, Any]:
        """Generate a comprehensive statistics report.
        
        Args:
            schema_name: Schema to report on
            include_queries: Whether to include query analysis
            
        Returns:
            Dictionary containing the complete report
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "schema": schema_name,
            "summary": {},
            "tables": {},
            "indexes": {},
            "queries": {},
            "recommendations": []
        }
        
        # Collect table statistics
        table_stats = await self.collect_table_stats(schema_name)
        
        # Calculate summary statistics
        total_size = sum(t.total_size for t in table_stats)
        total_rows = sum(t.row_count for t in table_stats)
        total_dead_tuples = sum(t.dead_tuple_count for t in table_stats)
        
        report["summary"] = {
            "total_tables": len(table_stats),
            "total_size_bytes": total_size,
            "total_size_pretty": self._format_bytes(total_size),
            "total_rows": total_rows,
            "total_dead_tuples": total_dead_tuples,
            "dead_tuple_ratio": total_dead_tuples / total_rows if total_rows > 0 else 0
        }
        
        # Add table details
        for stats in table_stats:
            report["tables"][stats.table_name] = {
                "size": self._format_bytes(stats.total_size),
                "rows": stats.row_count,
                "table_size": self._format_bytes(stats.table_size),
                "indexes_size": self._format_bytes(stats.indexes_size),
                "dead_tuples": stats.dead_tuple_count,
                "bloat_ratio": (
                    stats.dead_tuple_count / stats.row_count if stats.row_count > 0 else 0
                ),
                "last_vacuum": stats.last_vacuum.isoformat() if stats.last_vacuum else None,
                "last_analyze": stats.last_analyze.isoformat() if stats.last_analyze else None
            }
        
        # Get index statistics
        index_analysis = await self._get_index_summary(schema_name)
        report["indexes"] = index_analysis
        
        # Get query patterns if requested
        if include_queries:
            try:
                query_patterns = await self.analyze_query_patterns()
                report["queries"] = {
                    "total_patterns": len(query_patterns),
                    "top_by_total_time": self._get_top_queries_by_time(query_patterns),
                    "top_by_frequency": self._get_top_queries_by_count(query_patterns),
                    "slowest_queries": self._get_slowest_queries(query_patterns)
                }
            except MetadataError:
                report["queries"]["error"] = "pg_stat_statements not available"
        
        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(report)
        
        return report
    
    async def _get_index_summary(self, schema_name: str) -> dict[str, Any]:
        """Get summary of index statistics."""
        query = """
        SELECT 
            COUNT(*) as total_indexes,
            COUNT(*) FILTER (WHERE idx_scan = 0) as unused_indexes,
            SUM(pg_relation_size(indexrelid)) as total_index_size,
            COUNT(*) FILTER (WHERE indisunique) as unique_indexes,
            COUNT(*) FILTER (WHERE indisprimary) as primary_keys
        FROM pg_stat_user_indexes s
        JOIN pg_index i ON s.indexrelid = i.indexrelid
        WHERE s.schemaname = %s
        """
        
        result = await self.connection.fetch_one(query, (schema_name,))
        
        return {
            "total_indexes": result["total_indexes"],
            "unused_indexes": result["unused_indexes"],
            "total_size": self._format_bytes(result["total_index_size"] or 0),
            "unique_indexes": result["unique_indexes"],
            "primary_keys": result["primary_keys"]
        }
    
    def _get_top_queries_by_time(
        self, patterns: list[QueryPattern], limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top queries by total execution time."""
        sorted_patterns = sorted(patterns, key=lambda p: p.total_execution_time_ms, reverse=True)
        
        return [
            {
                "query_template": (
                    p.query_template[:100] + "..." 
                    if len(p.query_template) > 100 else p.query_template
                ),
                "total_time_ms": p.total_execution_time_ms,
                "avg_time_ms": p.avg_execution_time_ms,
                "execution_count": p.execution_count,
                "tables": p.tables_referenced
            }
            for p in sorted_patterns[:limit]
        ]
    
    def _get_top_queries_by_count(
        self, patterns: list[QueryPattern], limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top queries by execution count."""
        sorted_patterns = sorted(patterns, key=lambda p: p.execution_count, reverse=True)
        
        return [
            {
                "query_template": (
                    p.query_template[:100] + "..." 
                    if len(p.query_template) > 100 else p.query_template
                ),
                "execution_count": p.execution_count,
                "avg_time_ms": p.avg_execution_time_ms,
                "tables": p.tables_referenced
            }
            for p in sorted_patterns[:limit]
        ]
    
    def _get_slowest_queries(
        self, patterns: list[QueryPattern], limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get slowest queries by average execution time."""
        sorted_patterns = sorted(patterns, key=lambda p: p.avg_execution_time_ms, reverse=True)
        
        return [
            {
                "query_template": (
                    p.query_template[:100] + "..." 
                    if len(p.query_template) > 100 else p.query_template
                ),
                "avg_time_ms": p.avg_execution_time_ms,
                "max_time_ms": p.max_execution_time_ms,
                "execution_count": p.execution_count,
                "tables": p.tables_referenced
            }
            for p in sorted_patterns[:limit]
        ]
    
    def _generate_recommendations(self, report: dict[str, Any]) -> list[str]:
        """Generate recommendations based on the report."""
        recommendations = []
        
        # Check for bloated tables
        for table_name, table_info in report["tables"].items():
            if table_info["bloat_ratio"] > 0.2:  # 20% dead tuples
                recommendations.append(
                    f"Table '{table_name}' has {table_info['bloat_ratio']*100:.1f}% dead tuples. "
                    "Consider running VACUUM."
                )
            
            # Check for tables that haven't been analyzed recently
            if table_info["last_analyze"]:
                last_analyze = datetime.fromisoformat(table_info["last_analyze"])
                if datetime.now() - last_analyze > timedelta(days=7):
                    recommendations.append(
                        f"Table '{table_name}' hasn't been analyzed in over 7 days. "
                        "Consider running ANALYZE."
                    )
        
        # Check for unused indexes
        if report["indexes"].get("unused_indexes", 0) > 0:
            recommendations.append(
                f"Found {report['indexes']['unused_indexes']} unused indexes. "
                "Consider dropping them to save storage and improve write performance."
            )
        
        # Check for slow queries
        if "queries" in report and "slowest_queries" in report["queries"]:
            slow_queries = report["queries"]["slowest_queries"]
            if slow_queries and slow_queries[0]["avg_time_ms"] > 1000:
                recommendations.append(
                    "Found queries with average execution time over 1 second. "
                    "Consider optimizing these queries or adding appropriate indexes."
                )
        
        return recommendations
    
    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"
    
    async def start_continuous_collection(self, schema_name: str = "public",
                                        interval_minutes: int = 60) -> None:
        """Start continuous statistics collection.
        
        Args:
            schema_name: Schema to monitor
            interval_minutes: Collection interval in minutes
        """
        self._collection_interval = timedelta(minutes=interval_minutes)
        
        while True:
            try:
                # Collect statistics
                await self.collect_table_stats(schema_name)
                
                # Try to collect query patterns
                with contextlib.suppress(MetadataError):
                    # pg_stat_statements not available
                    await self.analyze_query_patterns()
                
                self._last_collection_time = datetime.now()
                
                # Wait for next collection
                await asyncio.sleep(self._collection_interval.total_seconds())
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue
                print(f"Error in continuous collection: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    def get_last_collection_time(self) -> datetime | None:
        """Get the last time statistics were collected."""
        return self._last_collection_time
    
    def clear_cache(self) -> None:
        """Clear the statistics cache."""
        self._stats_cache.clear()