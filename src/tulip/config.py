"""
TULIP Configuration Module

Configuration management for AmsterdamUMCdb access via BigQuery.
This module enforces BigQuery-only access as per EULA requirements.

EULA COMPLIANCE NOTES:
- Data must only be accessed via Google Cloud Platform (BigQuery)
- No local downloading, copying, or moving of the database
- Access is time-limited (January-February 2026 for ESICM Datathon)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "tulip"
FULL_NAME = "Tool for UMCdb Language Interface and Processing"
DATABASE_NAME = "AmsterdamUMCdb"
DATATHON_NAME = "Van Gogh"

# Setup logging with privacy-aware configuration
# CRITICAL: Logs should NEVER contain query results or patient data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(APP_NAME)


# -------------------------------------------------------------------
# EULA Compliance: Datathon Time Window
# -------------------------------------------------------------------
DATATHON_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DATATHON_END = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)


def is_within_datathon_period() -> bool:
    """Check if current time is within the allowed datathon period."""
    now = datetime.now(timezone.utc)
    return DATATHON_START <= now <= DATATHON_END


def get_datathon_period_status() -> str:
    """Get human-readable status of the datathon period."""
    now = datetime.now(timezone.utc)
    if now < DATATHON_START:
        return f"⏳ Datathon has not started yet. Starts: {DATATHON_START.strftime('%Y-%m-%d')}"
    elif now > DATATHON_END:
        return f"⚠️ Datathon period has ended ({DATATHON_END.strftime('%Y-%m-%d')}). Access may be restricted."
    else:
        days_remaining = (DATATHON_END - now).days
        return f"✅ Within datathon period. {days_remaining} days remaining until {DATATHON_END.strftime('%Y-%m-%d')}"


# -------------------------------------------------------------------
# Configuration Directory (for non-sensitive settings only)
# -------------------------------------------------------------------
def _get_config_dir() -> Path:
    """Get configuration directory. Uses home directory for consistency."""
    config_dir = Path.home() / ".tulip"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


_CONFIG_DIR = _get_config_dir()
_RUNTIME_CONFIG_PATH = _CONFIG_DIR / "config.json"


# -------------------------------------------------------------------
# AmsterdamUMCdb Dataset Configuration
# BigQuery-only access as per EULA requirements
# -------------------------------------------------------------------

# OMOP CDM Tables in AmsterdamUMCdb
# These are the 7 core tables available in the database
#
# NOTE: Column details are queried dynamically from BigQuery INFORMATION_SCHEMA
# via the get_table_info() MCP tool to ensure accuracy.
# See: https://ohdsi.github.io/CommonDataModel/cdm54.html
UMCDB_TABLES = {
    "person": {
        "description": "Patient demographics (de-identified)",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#person",
        "notes": "Contains de-identified patient information. Use get_table_info() to see all columns.",
    },
    "visit_occurrence": {
        "description": "ICU admission records",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#visit_occurrence",
        "notes": "Records hospital/ICU visits. Dates are shifted for de-identification.",
    },
    "death": {
        "description": "Mortality records",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#death",
        "notes": "Contains death records. Dates shifted for de-identification.",
    },
    "condition_occurrence": {
        "description": "Diagnoses and clinical conditions",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#condition_occurrence",
        "notes": "ICD-coded diagnoses and clinical conditions.",
    },
    "drug_exposure": {
        "description": "Medication administration records",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#drug_exposure",
        "notes": "Medication records including dosing information.",
    },
    "procedure_occurrence": {
        "description": "Clinical procedures performed",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#procedure_occurrence",
        "notes": "Includes interventions, surgeries, and other procedures.",
    },
    "measurement": {
        "description": "Clinical measurements and observations",
        "omop_docs": "https://ohdsi.github.io/CommonDataModel/cdm54.html#measurement",
        "notes": "Contains ~1 billion clinical observations. Use get_table_info() to see all columns.",
    },
}

# BigQuery Configuration
# The dataset location should be provided by datathon organizers
DEFAULT_BIGQUERY_PROJECT = os.getenv("TULIP_BQ_PROJECT", "")
DEFAULT_BIGQUERY_DATASET = os.getenv("TULIP_BQ_DATASET", "")


def get_bigquery_table_path(table_name: str) -> str:
    """
    Get fully qualified BigQuery table path.
    
    Format: `project.dataset.table`
    Supports dataset in different project (dataset_project.dataset.table)
    """
    config = get_bigquery_config()
    dataset_project = config.get("dataset_project", config["project"])
    dataset = config["dataset"]
    
    if not dataset_project or not dataset:
        raise ValueError(
            "BigQuery project and dataset must be configured. "
            "Set TULIP_BQ_PROJECT and TULIP_BQ_DATASET environment variables."
        )
    
    return f"`{dataset_project}.{dataset}.{table_name}`"


def get_available_tables() -> list[str]:
    """Return list of available table names."""
    return list(UMCDB_TABLES.keys())


def get_table_info(table_name: str) -> dict | None:
    """Get information about a specific table."""
    return UMCDB_TABLES.get(table_name.lower())


# -------------------------------------------------------------------
# Runtime Configuration (non-sensitive settings only)
# -------------------------------------------------------------------

def _get_default_runtime_config() -> dict:
    """Default runtime configuration."""
    return {
        "bigquery_project": "",  # Project for authentication/billing
        "bigquery_dataset_project": "",  # Project where dataset lives (if different)
        "bigquery_dataset": "",
        "bigquery_location": "EU",  # Default location (EU, US, etc.)
        "query_limit_default": 100,
        "query_limit_max": 1000,
        # SECURITY: Never log query results
        "log_queries": False,  # Log query structure only, never results
        "log_level": "INFO",
        # LMStudio configuration
        "lmstudio_host": "http://localhost:1234",
        "model_name": "gpt-oss-20b",
    }


def load_runtime_config() -> dict:
    """Load runtime configuration from config file."""
    if _RUNTIME_CONFIG_PATH.exists():
        try:
            with open(_RUNTIME_CONFIG_PATH) as f:
                config = json.load(f)
                # Merge with defaults to ensure all keys exist
                defaults = _get_default_runtime_config()
                defaults.update(config)
                return defaults
        except Exception as e:
            logger.warning(f"Could not parse runtime config: {e}. Using defaults.")
    return _get_default_runtime_config()


def save_runtime_config(config: dict) -> None:
    """Save runtime configuration to config file."""
    # SECURITY: Ensure sensitive data is not stored
    safe_config = {k: v for k, v in config.items() if not k.startswith("_")}
    
    with open(_RUNTIME_CONFIG_PATH, "w") as f:
        json.dump(safe_config, indent=2, fp=f)
    
    logger.info(f"Configuration saved to {_RUNTIME_CONFIG_PATH}")


def get_bigquery_config() -> dict:
    """Get BigQuery configuration from environment and config file."""
    config = load_runtime_config()
    
    project = os.getenv("TULIP_BQ_PROJECT", config.get("bigquery_project", ""))
    dataset_project = os.getenv("TULIP_BQ_DATASET_PROJECT", config.get("bigquery_dataset_project", ""))
    
    return {
        "project": project,  # Project for authentication/billing
        "dataset_project": dataset_project if dataset_project else project,  # Project where dataset lives
        "dataset": os.getenv("TULIP_BQ_DATASET", config.get("bigquery_dataset", "")),
        "location": os.getenv("TULIP_BQ_LOCATION", config.get("bigquery_location", "EU")),
    }


def validate_bigquery_config() -> tuple[bool, str]:
    """
    Validate BigQuery configuration is complete.
    
    Returns:
        Tuple of (is_valid, message)
    """
    config = get_bigquery_config()
    
    if not config["project"]:
        return False, "TULIP_BQ_PROJECT environment variable not set"
    
    if not config["dataset"]:
        return False, "TULIP_BQ_DATASET environment variable not set"
    
    return True, f"BigQuery configured: {config['project']}.{config['dataset']}"


# -------------------------------------------------------------------
# Security Configuration
# -------------------------------------------------------------------

# Maximum number of rows that can be returned in a single query
MAX_QUERY_ROWS = 1000

# Columns that should never be exposed in raw form (additional protection)
# These are already de-identified in AmsterdamUMCdb, but we add extra protection
SENSITIVE_COLUMN_PATTERNS = [
    "name",
    "address", 
    "phone",
    "email",
    "ssn",
    "social_security",
    "mrn",
    "medical_record",
    "insurance",
]

# Query patterns that could potentially be used for re-identification
REIDENTIFICATION_RISK_PATTERNS = [
    # Direct identifier searches
    r"where\s+.*\s*=\s*['\"].*['\"]",  # Searching for specific string values
    # Uniqueness attacks
    r"having\s+count\s*\(\s*\*\s*\)\s*=\s*1",  # Finding unique records
    # Extreme value attacks
    r"(min|max)\s*\(\s*(age|year_of_birth)\s*\)",
    # Small group attacks
    r"group\s+by.*having\s+count\s*\(\s*\*\s*\)\s*<\s*\d+",
]

# Minimum aggregation size for grouped results (k-anonymity protection)
MIN_GROUP_SIZE = 5


def get_security_config() -> dict:
    """Get security-related configuration."""
    return {
        "max_query_rows": MAX_QUERY_ROWS,
        "sensitive_column_patterns": SENSITIVE_COLUMN_PATTERNS,
        "reidentification_risk_patterns": REIDENTIFICATION_RISK_PATTERNS,
        "min_group_size": MIN_GROUP_SIZE,
        "enforce_datathon_period": True,
    }

