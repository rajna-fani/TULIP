"""
Tests for TULIP security module.

These tests verify that security controls work correctly to prevent:
- SQL injection
- Re-identification attacks
- EULA violations
"""

import pytest


class TestQueryValidation:
    """Tests for SQL query validation and security checks."""

    def test_blocks_multiple_statements(self):
        """Multiple SQL statements should be blocked (injection vector)."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person LIMIT 10; DROP TABLE person;"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "multiple" in message.lower() or "injection" in message.lower()

    def test_blocks_write_operations(self):
        """Write operations (INSERT, UPDATE, DELETE, etc.) should be blocked."""
        from tulip.security import validate_query_security
        
        write_queries = [
            "INSERT INTO person VALUES (1, 2, 3)",
            "UPDATE person SET gender = 1",
            "DELETE FROM person WHERE person_id = 1",
            "DROP TABLE person",
            "CREATE TABLE test (id INT)",
        ]
        
        for query in write_queries:
            is_safe, message, _ = validate_query_security(query)
            assert not is_safe, f"Should block: {query}"

    def test_allows_select_with_limit(self):
        """Valid SELECT queries with LIMIT should be allowed."""
        from tulip.security import validate_query_security
        
        query = "SELECT gender_concept_id, COUNT(*) FROM person GROUP BY 1 LIMIT 100"
        is_safe, message, _ = validate_query_security(query)
        
        assert is_safe, f"Should allow valid query: {message}"

    def test_requires_limit_clause(self):
        """Queries without LIMIT should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "limit" in message.lower()

    def test_blocks_excessive_limit(self):
        """LIMIT exceeding maximum should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person LIMIT 10000"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "limit" in message.lower() or "exceed" in message.lower()


class TestReidentificationProtection:
    """Tests for re-identification attack prevention."""

    def test_blocks_direct_patient_lookup(self):
        """Direct person_id lookups should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person WHERE person_id = 12345 LIMIT 10"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "person_id" in message.lower() or "reidentification" in message.lower()

    def test_blocks_unique_record_queries(self):
        """Queries finding unique records should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person GROUP BY 1 HAVING COUNT(*) = 1 LIMIT 100"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe

    def test_blocks_small_group_queries(self):
        """Queries with very small group sizes should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person GROUP BY 1 HAVING COUNT(*) < 3 LIMIT 100"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "group size" in message.lower() or "privacy" in message.lower()


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limiter_allows_initial_queries(self):
        """Rate limiter should allow queries within limits."""
        from tulip.security import RateLimiter
        
        limiter = RateLimiter(max_queries_per_hour=100, max_queries_per_minute=10)
        
        allowed, message = limiter.check_rate_limit()
        assert allowed
        assert message == "OK"

    def test_rate_limiter_blocks_excessive_queries(self):
        """Rate limiter should block queries exceeding per-minute limit."""
        from tulip.security import RateLimiter
        
        limiter = RateLimiter(max_queries_per_hour=100, max_queries_per_minute=3)
        
        # Record queries up to limit
        for _ in range(3):
            limiter.record_query()
        
        # Next query should be blocked
        allowed, message = limiter.check_rate_limit()
        assert not allowed
        assert "rate limit" in message.lower()


class TestAuditLogging:
    """Tests for privacy-preserving audit logging."""

    def test_audit_log_does_not_store_results(self):
        """Audit log should never store query results."""
        from tulip.security import QueryAuditLog
        
        log = QueryAuditLog()
        
        log.log_query(
            query_hash="abc123",
            tables_accessed=["person"],
            query_type="SELECT",
            success=True,
            execution_time_ms=100.0,
        )
        
        # Check that no result data is stored
        assert len(log.entries) == 1
        entry = log.entries[0]
        
        assert "result" not in entry
        assert "data" not in entry
        assert "value" not in entry

    def test_audit_log_truncates_hash(self):
        """Audit log should truncate query hashes for privacy."""
        from tulip.security import QueryAuditLog
        
        log = QueryAuditLog()
        full_hash = "a" * 64  # Full SHA-256 hash
        
        log.log_query(
            query_hash=full_hash,
            tables_accessed=["person"],
            query_type="SELECT",
            success=True,
        )
        
        entry = log.entries[0]
        assert len(entry["query_hash"]) == 16  # Truncated


class TestSQLInjectionProtection:
    """Tests for SQL injection prevention."""

    def test_blocks_union_injection(self):
        """UNION-based injection should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person UNION SELECT * FROM death LIMIT 100"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe
        assert "injection" in message.lower() or "union" in message.lower()

    def test_blocks_comment_injection(self):
        """Comment-based injection should be blocked."""
        from tulip.security import validate_query_security
        
        query = "SELECT * FROM person; -- malicious comment LIMIT 100"
        is_safe, message, _ = validate_query_security(query)
        
        assert not is_safe

    def test_blocks_time_based_injection(self):
        """Time-based injection attempts should be blocked."""
        from tulip.security import validate_query_security
        
        queries = [
            "SELECT * FROM person WHERE SLEEP(10) LIMIT 100",
            "SELECT BENCHMARK(1000000, SHA1('test')) FROM person LIMIT 100",
        ]
        
        for query in queries:
            is_safe, message, _ = validate_query_security(query)
            assert not is_safe, f"Should block: {query}"

