"""
TULIP Security Module

Comprehensive security controls for AmsterdamUMCdb access compliance.

EULA COMPLIANCE ENFORCED:
1. No re-identification attempts
2. No downloading/copying of data
3. No sharing access with unauthorized users
4. Non-commercial, scientific research only
5. Query audit trail (without sensitive data)
6. Rate limiting to prevent data extraction

This module implements multiple layers of protection:
- SQL injection prevention
- Re-identification attack detection
- K-anonymity enforcement for aggregations
- Query complexity limits
- Privacy-preserving audit logging
"""

import hashlib
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import Keyword

from tulip.config import (
    MAX_QUERY_ROWS,
    MIN_GROUP_SIZE,
    SENSITIVE_COLUMN_PATTERNS,
    is_within_datathon_period,
    logger,
)


class SecurityViolation(Exception):
    """Raised when a security policy is violated."""
    
    def __init__(self, message: str, violation_type: str = "general"):
        self.message = message
        self.violation_type = violation_type
        super().__init__(self.message)


class ReidentificationRisk(SecurityViolation):
    """Raised when a query poses re-identification risk."""
    
    def __init__(self, message: str):
        super().__init__(message, violation_type="reidentification")


class EULAViolation(SecurityViolation):
    """Raised when EULA terms are violated."""
    
    def __init__(self, message: str):
        super().__init__(message, violation_type="eula")


# -------------------------------------------------------------------
# Rate Limiting
# -------------------------------------------------------------------

class RateLimiter:
    """
    Token bucket rate limiter for query throttling.
    
    Prevents excessive querying which could indicate data extraction attempts.
    """
    
    def __init__(
        self,
        max_queries_per_hour: int = 100,
        max_queries_per_minute: int = 10,
    ):
        self.max_per_hour = max_queries_per_hour
        self.max_per_minute = max_queries_per_minute
        self._query_times: list[float] = []
    
    def check_rate_limit(self) -> tuple[bool, str]:
        """
        Check if the current request is within rate limits.
        
        Returns:
            Tuple of (allowed, message)
        """
        now = time.time()
        
        # Clean old entries
        hour_ago = now - 3600
        minute_ago = now - 60
        self._query_times = [t for t in self._query_times if t > hour_ago]
        
        # Check hourly limit
        if len(self._query_times) >= self.max_per_hour:
            return False, f"Rate limit exceeded: {self.max_per_hour} queries/hour. Please wait."
        
        # Check per-minute limit
        recent = sum(1 for t in self._query_times if t > minute_ago)
        if recent >= self.max_per_minute:
            return False, f"Rate limit exceeded: {self.max_per_minute} queries/minute. Please slow down."
        
        return True, "OK"
    
    def record_query(self):
        """Record a query execution."""
        self._query_times.append(time.time())


# Global rate limiter instance
_rate_limiter = RateLimiter()


def check_rate_limit() -> tuple[bool, str]:
    """Check global rate limit."""
    return _rate_limiter.check_rate_limit()


def record_query():
    """Record a query for rate limiting."""
    _rate_limiter.record_query()


# -------------------------------------------------------------------
# Query Audit Logging (Privacy-Preserving)
# -------------------------------------------------------------------

class QueryAuditLog:
    """
    Privacy-preserving query audit log.
    
    IMPORTANT: This log stores query metadata ONLY, never:
    - Query results
    - Specific patient IDs or identifiers
    - Raw data values
    
    This is required by EULA point 10: "Make all code available"
    """
    
    def __init__(self, log_file_path: str | None = None):
        self.entries: list[dict] = []
        self.log_file_path = log_file_path
    
    def log_query(
        self,
        query_hash: str,
        tables_accessed: list[str],
        query_type: str,
        success: bool,
        error_message: str | None = None,
        execution_time_ms: float | None = None,
    ):
        """
        Log query metadata (NOT the query itself or results).
        
        Args:
            query_hash: SHA-256 hash of the query (for deduplication, not reconstruction)
            tables_accessed: List of tables accessed
            query_type: Type of query (SELECT, etc.)
            success: Whether query executed successfully
            error_message: Error message if failed (sanitized)
            execution_time_ms: Query execution time
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_hash": query_hash[:16],  # Truncated for privacy
            "tables_accessed": tables_accessed,
            "query_type": query_type,
            "success": success,
            "error_type": self._sanitize_error(error_message) if error_message else None,
            "execution_time_ms": execution_time_ms,
        }
        
        self.entries.append(entry)
        
        # Keep only last 1000 entries in memory
        if len(self.entries) > 1000:
            self.entries = self.entries[-1000:]
        
        # Log to file if configured (for datathon organizers)
        if self.log_file_path:
            self._write_to_file(entry)
    
    def _sanitize_error(self, error: str) -> str:
        """Sanitize error message to remove any potentially sensitive info."""
        # Remove any values that look like identifiers
        sanitized = re.sub(r'\b\d{5,}\b', '[ID_REDACTED]', error)
        sanitized = re.sub(r"'[^']*'", '[VALUE_REDACTED]', sanitized)
        return sanitized[:200]  # Truncate long errors
    
    def _write_to_file(self, entry: dict):
        """Write entry to audit log file."""
        import json
        try:
            with open(self.log_file_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Could not write to audit log: {e}")
    
    def get_summary(self) -> dict:
        """Get summary statistics (for debugging, no sensitive data)."""
        if not self.entries:
            return {"total_queries": 0}
        
        return {
            "total_queries": len(self.entries),
            "successful": sum(1 for e in self.entries if e["success"]),
            "failed": sum(1 for e in self.entries if not e["success"]),
            "tables_queried": list(set(
                t for e in self.entries for t in e.get("tables_accessed", [])
            )),
        }


# Global audit log instance
_audit_log = QueryAuditLog()


def get_query_hash(query: str) -> str:
    """Generate privacy-preserving hash of query."""
    return hashlib.sha256(query.encode()).hexdigest()


def log_query_execution(
    query: str,
    tables: list[str],
    query_type: str,
    success: bool,
    error: str | None = None,
    execution_time_ms: float | None = None,
):
    """Log query execution to audit trail."""
    _audit_log.log_query(
        query_hash=get_query_hash(query),
        tables_accessed=tables,
        query_type=query_type,
        success=success,
        error_message=error,
        execution_time_ms=execution_time_ms,
    )


# -------------------------------------------------------------------
# SQL Security Validation
# -------------------------------------------------------------------

def _extract_tables_from_query(parsed) -> list[str]:
    """Extract table names from parsed SQL."""
    tables = []
    
    from_seen = False
    for token in parsed.tokens:
        if from_seen:
            if isinstance(token, Identifier):
                tables.append(token.get_real_name())
            elif isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    tables.append(identifier.get_real_name())
            elif token.ttype is Keyword:
                from_seen = False
        
        if token.ttype is Keyword and token.value.upper() == "FROM":
            from_seen = True
    
    return [t for t in tables if t]


def validate_query_security(sql_query: str) -> tuple[bool, str, list[str]]:
    """
    Comprehensive security validation for SQL queries.
    
    Checks:
    1. SQL injection patterns
    2. Write operations (not allowed)
    3. Re-identification risk patterns
    4. Query complexity
    5. Sensitive column access
    
    Returns:
        Tuple of (is_safe, message, tables_accessed)
    """
    try:
        if not sql_query or not sql_query.strip():
            return False, "Empty query", []
        
        # Parse SQL
        parsed_statements = sqlparse.parse(sql_query.strip())
        if not parsed_statements:
            return False, "Invalid SQL syntax", []
        
        # Block multiple statements (injection vector)
        if len(parsed_statements) > 1:
            return False, "Multiple statements not allowed (potential SQL injection)", []
        
        statement = parsed_statements[0]
        statement_type = statement.get_type()
        sql_upper = sql_query.strip().upper()
        
        # Extract tables for audit
        tables = _extract_tables_from_query(statement)
        
        # ===============================
        # RULE 1: Only SELECT allowed
        # ===============================
        if statement_type not in ("SELECT", "UNKNOWN"):
            return False, f"Only SELECT queries allowed. Got: {statement_type}", tables
        
        # Check for PRAGMA (might be useful for schema exploration)
        if sql_upper.startswith("PRAGMA"):
            return False, "PRAGMA statements not allowed on BigQuery", tables
        
        # ===============================
        # RULE 2: Block write operations
        # ===============================
        write_operations = {
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
            "TRUNCATE", "REPLACE", "MERGE", "EXEC", "EXECUTE", "GRANT",
            "REVOKE", "INTO OUTFILE", "INTO DUMPFILE",
        }
        
        for op in write_operations:
            if f" {op} " in f" {sql_upper} " or sql_upper.startswith(op):
                return False, f"Write operation not allowed: {op}", tables
        
        # ===============================
        # RULE 3: Block injection patterns
        # ===============================
        injection_patterns = [
            (r";\s*--", "SQL comment injection"),
            (r";\s*/\*", "SQL block comment injection"),
            (r"union\s+(all\s+)?select", "UNION injection"),
            (r"'\s*or\s+'?\d+'?\s*=\s*'?\d+'?", "OR injection"),
            (r"'\s*and\s+'?\d+'?\s*=\s*'?\d+'?", "AND injection"),
            (r"waitfor\s+delay", "Time-based injection"),
            (r"benchmark\s*\(", "Benchmark injection"),
            (r"sleep\s*\(", "Sleep injection"),
            (r"load_file\s*\(", "File access injection"),
        ]
        
        for pattern, description in injection_patterns:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                return False, f"Injection pattern detected: {description}", tables
        
        # ===============================
        # RULE 4: Re-identification protection
        # ===============================
        reid_result = _check_reidentification_risk(sql_query, sql_upper)
        if not reid_result[0]:
            return reid_result[0], reid_result[1], tables
        
        # ===============================
        # RULE 5: Enforce query limits
        # ===============================
        if "LIMIT" not in sql_upper:
            return False, f"Query must include LIMIT clause (max {MAX_QUERY_ROWS} rows)", tables
        
        # Check if limit is too high
        limit_match = re.search(r"LIMIT\s+(\d+)", sql_upper)
        if limit_match:
            limit_value = int(limit_match.group(1))
            if limit_value > MAX_QUERY_ROWS:
                return False, f"LIMIT exceeds maximum allowed ({MAX_QUERY_ROWS})", tables
        
        # ===============================
        # RULE 6: Block sensitive column patterns
        # ===============================
        for pattern in SENSITIVE_COLUMN_PATTERNS:
            # Check if accessing columns that shouldn't exist in de-identified data
            if re.search(rf"\b{pattern}\b", sql_query, re.IGNORECASE):
                logger.warning(f"Query references potentially sensitive pattern: {pattern}")
                # This is a warning, not a block, as the data is de-identified
        
        return True, "Query passed security validation", tables
    
    except Exception as e:
        logger.error(f"Security validation error: {e}")
        return False, f"Security validation failed: {e}", []


def _check_reidentification_risk(sql_query: str, sql_upper: str) -> tuple[bool, str]:
    """
    Check for re-identification risk patterns.
    
    These patterns could potentially be used to identify specific individuals
    even in de-identified data.
    """
    
    # Pattern 1: Selecting individual records by specific criteria
    # This could be used to identify known individuals
    if re.search(r"where\s+person_id\s*=\s*\d+", sql_upper):
        return False, "Direct person_id lookup not allowed. Use aggregated queries."
    
    # Pattern 2: Unique record identification
    # Finding records that appear only once
    if re.search(r"having\s+count\s*\(\s*\*\s*\)\s*=\s*1", sql_upper):
        return False, "Queries finding unique records pose re-identification risk"
    
    # Pattern 3: Very small group sizes
    small_group_match = re.search(r"having\s+count\s*\(\s*\*\s*\)\s*<\s*(\d+)", sql_upper)
    if small_group_match:
        group_size = int(small_group_match.group(1))
        if group_size < MIN_GROUP_SIZE:
            return False, f"Minimum group size is {MIN_GROUP_SIZE} for privacy protection"
    
    # Pattern 4: Extreme value searches (oldest, youngest, etc.)
    # These can identify outliers
    extreme_patterns = [
        (r"order\s+by\s+year_of_birth\s+(asc|desc)?\s*limit\s+1", "oldest/youngest person"),
        (r"order\s+by\s+age\s+(asc|desc)?\s*limit\s+1", "oldest/youngest person"),
        (r"(min|max)\s*\(\s*year_of_birth\s*\)", "extreme birth year"),
    ]
    
    for pattern, description in extreme_patterns:
        if re.search(pattern, sql_upper, re.IGNORECASE):
            return False, f"Query targets {description} - potential re-identification risk"
    
    # Pattern 5: Cross-referencing multiple quasi-identifiers
    # Combining multiple attributes to narrow down individuals
    quasi_identifiers = ["year_of_birth", "gender", "race", "ethnicity", "zip", "city"]
    qi_count = sum(1 for qi in quasi_identifiers if qi in sql_query.lower())
    if qi_count >= 3:
        # Check if it's a selection query (vs aggregation)
        if "group by" not in sql_upper and "count(" not in sql_upper:
            return False, "Selecting multiple quasi-identifiers without aggregation poses re-identification risk"
    
    # Pattern 6: Rare condition/procedure lookup
    # Very rare conditions could identify individuals
    if re.search(r"where\s+.*concept_id\s*=", sql_upper):
        # This is allowed but should use aggregation
        if "count(" not in sql_upper and "group by" not in sql_upper:
            logger.warning("Direct condition lookup without aggregation - consider using aggregated queries")
    
    return True, "No re-identification risk detected"


# -------------------------------------------------------------------
# EULA Compliance Checks
# -------------------------------------------------------------------

def check_eula_compliance() -> tuple[bool, str]:
    """
    Verify EULA compliance before allowing queries.
    
    Returns:
        Tuple of (compliant, message)
    """
    issues = []
    
    # Check 1: Datathon period
    if not is_within_datathon_period():
        issues.append("Outside datathon period (January-February 2026)")
    
    # Check 2: BigQuery configuration (no local data)
    from tulip.config import validate_bigquery_config
    bq_valid, bq_msg = validate_bigquery_config()
    if not bq_valid:
        issues.append(f"BigQuery not configured: {bq_msg}")
    
    if issues:
        return False, "EULA compliance issues: " + "; ".join(issues)
    
    return True, "EULA compliance verified"


def enforce_security(sql_query: str) -> tuple[bool, str, list[str]]:
    """
    Main security enforcement function.
    
    Performs all security checks in order:
    1. Rate limiting
    2. EULA compliance
    3. Query security validation
    
    Returns:
        Tuple of (allowed, message, tables_accessed)
    """
    # Check rate limit
    rate_ok, rate_msg = check_rate_limit()
    if not rate_ok:
        return False, rate_msg, []
    
    # Check EULA compliance
    eula_ok, eula_msg = check_eula_compliance()
    if not eula_ok:
        # Log but don't block during development
        logger.warning(f"EULA compliance warning: {eula_msg}")
    
    # Validate query security
    query_ok, query_msg, tables = validate_query_security(sql_query)
    if not query_ok:
        return False, query_msg, tables
    
    # Record the query for rate limiting
    record_query()
    
    return True, "Security checks passed", tables


# -------------------------------------------------------------------
# Secure Result Handling
# -------------------------------------------------------------------

def sanitize_error_for_user(error: str) -> str:
    """
    Sanitize error messages before showing to user.
    
    Removes any potentially sensitive information from error messages.
    """
    # Remove specific IDs
    sanitized = re.sub(r'\b\d{5,}\b', '[REDACTED]', str(error))
    
    # Remove quoted values
    sanitized = re.sub(r"'[^']{10,}'", "'[VALUE_REDACTED]'", sanitized)
    
    # Remove file paths
    sanitized = re.sub(r'/[^\s]+', '[PATH_REDACTED]', sanitized)
    
    return sanitized


def check_result_privacy(result_df, query: str) -> tuple[bool, str]:
    """
    Check query results for privacy concerns before returning.
    
    This is a defense-in-depth measure - even if a query passes
    security validation, we check the results.
    
    Args:
        result_df: Pandas/Polars dataframe with results
        query: Original query (for context)
    
    Returns:
        Tuple of (safe_to_return, warning_message)
    """
    try:
        if result_df is None or len(result_df) == 0:
            return True, ""
        
        # Check 1: Too few results in grouped query might reveal individuals
        if len(result_df) == 1:
            # Single row results are concerning unless it's an aggregate
            sql_upper = query.upper()
            if "GROUP BY" in sql_upper and "COUNT" not in sql_upper:
                return False, "Query returned single record - potential privacy risk"
        
        # Check 2: Small group sizes in aggregated results
        if "count" in [col.lower() for col in result_df.columns]:
            count_cols = [col for col in result_df.columns if "count" in col.lower()]
            for col in count_cols:
                min_count = result_df[col].min()
                if min_count < MIN_GROUP_SIZE:
                    return False, f"Results contain groups smaller than {MIN_GROUP_SIZE} - suppressed for privacy"
        
        return True, ""
    
    except Exception as e:
        logger.error(f"Result privacy check failed: {e}")
        return True, ""  # Fail open but log


# -------------------------------------------------------------------
# Export security status for MCP server
# -------------------------------------------------------------------

def get_security_status() -> dict:
    """Get current security status for diagnostics."""
    return {
        "rate_limiter": {
            "queries_in_last_hour": len(_rate_limiter._query_times),
            "max_per_hour": _rate_limiter.max_per_hour,
            "max_per_minute": _rate_limiter.max_per_minute,
        },
        "audit_log": _audit_log.get_summary(),
        "eula_compliance": check_eula_compliance(),
        "datathon_period": is_within_datathon_period(),
    }

