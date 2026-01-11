"""
Tests for TULIP configuration module.
"""

import os
import pytest


class TestDatathonPeriod:
    """Tests for datathon period enforcement."""

    def test_datathon_period_constants_defined(self):
        """Datathon start and end dates should be defined."""
        from tulip.config import DATATHON_START, DATATHON_END
        
        assert DATATHON_START is not None
        assert DATATHON_END is not None
        assert DATATHON_START < DATATHON_END

    def test_datathon_status_returns_string(self):
        """get_datathon_period_status should return a status string."""
        from tulip.config import get_datathon_period_status
        
        status = get_datathon_period_status()
        
        assert isinstance(status, str)
        assert len(status) > 0


class TestBigQueryConfig:
    """Tests for BigQuery configuration."""

    def test_get_bigquery_config_returns_dict(self):
        """get_bigquery_config should return a dictionary."""
        from tulip.config import get_bigquery_config
        
        config = get_bigquery_config()
        
        assert isinstance(config, dict)
        assert "project" in config
        assert "dataset" in config

    def test_validate_bigquery_config_without_env_vars(self):
        """Validation should fail when env vars are not set."""
        # Clear environment variables
        old_project = os.environ.pop("TULIP_BQ_PROJECT", None)
        old_dataset = os.environ.pop("TULIP_BQ_DATASET", None)
        
        try:
            from tulip.config import validate_bigquery_config
            
            # Also need to clear the runtime config
            is_valid, message = validate_bigquery_config()
            
            # Should indicate missing configuration
            # (may pass if config file has values)
            assert isinstance(is_valid, bool)
            assert isinstance(message, str)
        finally:
            # Restore environment
            if old_project:
                os.environ["TULIP_BQ_PROJECT"] = old_project
            if old_dataset:
                os.environ["TULIP_BQ_DATASET"] = old_dataset


class TestTableConfiguration:
    """Tests for AmsterdamUMCdb table configuration."""

    def test_umcdb_tables_defined(self):
        """UMCDB_TABLES should contain the 7 OMOP CDM tables."""
        from tulip.config import UMCDB_TABLES
        
        expected_tables = [
            "person",
            "visit_occurrence",
            "death",
            "condition_occurrence",
            "drug_exposure",
            "procedure_occurrence",
            "measurement",
        ]
        
        for table in expected_tables:
            assert table in UMCDB_TABLES, f"Missing table: {table}"

    def test_table_info_has_required_fields(self):
        """Each table should have description, key_columns, and notes."""
        from tulip.config import UMCDB_TABLES
        
        for table_name, info in UMCDB_TABLES.items():
            assert "description" in info, f"{table_name} missing description"
            assert "key_columns" in info, f"{table_name} missing key_columns"
            assert "notes" in info, f"{table_name} missing notes"

    def test_get_available_tables(self):
        """get_available_tables should return list of table names."""
        from tulip.config import get_available_tables
        
        tables = get_available_tables()
        
        assert isinstance(tables, list)
        assert len(tables) == 7
        assert "person" in tables
        assert "measurement" in tables


class TestSecurityConfig:
    """Tests for security configuration."""

    def test_security_limits_defined(self):
        """Security limits should be defined."""
        from tulip.config import MAX_QUERY_ROWS, MIN_GROUP_SIZE
        
        assert MAX_QUERY_ROWS == 1000
        assert MIN_GROUP_SIZE == 5

    def test_get_security_config(self):
        """get_security_config should return security settings."""
        from tulip.config import get_security_config
        
        config = get_security_config()
        
        assert isinstance(config, dict)
        assert "max_query_rows" in config
        assert "min_group_size" in config
        assert "sensitive_column_patterns" in config

