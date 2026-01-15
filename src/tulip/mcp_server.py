"""
TULIP MCP Server - Tool for UMCdb Language Interface and Processing

Provides MCP tools for querying AmsterdamUMCdb via BigQuery.
Designed for use with local LLMs (e.g., LMStudio with gpt-oss-20b).

SECURITY ARCHITECTURE:
- All queries go through security validation (security.py)
- Re-identification protection is enforced
- Query results are never logged
- Rate limiting prevents data extraction
- Audit trail maintained for compliance

EULA COMPLIANCE:
- BigQuery-only access (no local data storage)
- Time-limited to datathon period
- All code is open source and available
"""

import os
import time
from pathlib import Path

import sqlparse
from fastmcp import FastMCP

from tulip.config import (
    APP_NAME,
    DATABASE_NAME,
    DATATHON_NAME,
    FULL_NAME,
    MAX_QUERY_ROWS,
    UMCDB_TABLES,
    get_bigquery_config,
    get_bigquery_table_path,
    get_datathon_period_status,
    get_table_info as get_table_info_config,
    is_within_datathon_period,
    logger,
    validate_bigquery_config,
)
from tulip.security import (
    enforce_security,
    get_security_status,
    log_query_execution,
    sanitize_error_for_user,
    check_result_privacy,
)

# Create FastMCP server instance
mcp = FastMCP(APP_NAME)

# Global BigQuery client
_bq_client = None
_bq_project = None


def _validate_limit(limit: int) -> bool:
    """Validate limit parameter to prevent resource exhaustion."""
    return isinstance(limit, int) and 0 < limit <= MAX_QUERY_ROWS


def _init_bigquery():
    """Initialize BigQuery client."""
    global _bq_client, _bq_project
    
    try:
        from google.cloud import bigquery
    except ImportError:
        raise ImportError(
            "BigQuery dependencies not found. Install with: pip install google-cloud-bigquery"
        )
    
    # Validate configuration
    is_valid, msg = validate_bigquery_config()
    if not is_valid:
        logger.error(f"BigQuery configuration error: {msg}")
        raise ValueError(msg)
    
    config = get_bigquery_config()
    _bq_project = config["project"]
    
    try:
        _bq_client = bigquery.Client(project=_bq_project)
        logger.info(f"BigQuery client initialized for project: {_bq_project}")
    except Exception as e:
        logger.error(f"Failed to initialize BigQuery client: {e}")
        raise RuntimeError(f"BigQuery initialization failed: {e}")


def _get_status_banner() -> str:
    """Get a status banner with system information."""
    config = get_bigquery_config()
    datathon_status = get_datathon_period_status()
    
    return f"""🌷 **{FULL_NAME} ({APP_NAME.upper()})**
📊 **Database:** {DATABASE_NAME}
🎨 **Datathon:** {DATATHON_NAME}
{datathon_status}
☁️ **BigQuery Project:** {config.get('project', 'Not configured')}
📁 **Dataset:** {config.get('dataset', 'Not configured')}
"""


# ==========================================
# INTERNAL QUERY EXECUTION FUNCTIONS
# ==========================================

def _execute_bigquery_query(sql_query: str) -> str:
    """
    Execute BigQuery query with security enforcement.
    
    SECURITY: This function enforces all security policies before
    executing any query against the database.
    """
    start_time = time.time()
    tables_accessed = []
    
    try:
        # Security enforcement (includes rate limiting, validation, etc.)
        is_safe, message, tables_accessed = enforce_security(sql_query)
        if not is_safe:
            log_query_execution(
                query=sql_query,
                tables=tables_accessed,
                query_type="BLOCKED",
                success=False,
                error=message,
            )
            return f"❌ **Security Error:** {message}"
        
        # Execute query
        from google.cloud import bigquery
        
        config = get_bigquery_config()
        job_config = bigquery.QueryJobConfig()
        location = config.get("location", "EU")  # Set dataset location
        query_job = _bq_client.query(sql_query, job_config=job_config, location=location)
        df = query_job.to_dataframe()
        
        execution_time = (time.time() - start_time) * 1000
        
        # Check result privacy before returning
        is_private, privacy_warning = check_result_privacy(df, sql_query)
        if not is_private:
            log_query_execution(
                query=sql_query,
                tables=tables_accessed,
                query_type="SELECT",
                success=False,
                error=privacy_warning,
                execution_time_ms=execution_time,
            )
            return f"❌ **Privacy Protection:** {privacy_warning}"
        
        # Log successful execution (without results!)
        log_query_execution(
            query=sql_query,
            tables=tables_accessed,
            query_type="SELECT",
            success=True,
            execution_time_ms=execution_time,
        )
        
        if df.empty:
            return "No results found"
        
        # Format results
        if len(df) > 50:
            result = df.head(50).to_string(index=False)
            result += f"\n... ({len(df)} total rows, showing first 50)"
        else:
            result = df.to_string(index=False)
        
        # Add privacy warning if results are small
        if len(df) < 10:
            result += "\n\n⚠️ **Note:** Small result sets may have limited statistical significance."
        
        return result
    
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        error_msg = sanitize_error_for_user(str(e))
        
        log_query_execution(
            query=sql_query,
            tables=tables_accessed,
            query_type="SELECT",
            success=False,
            error=error_msg,
            execution_time_ms=execution_time,
        )
        
        return _format_error_with_guidance(error_msg)


def _format_error_with_guidance(error: str) -> str:
    """Format error message with helpful guidance."""
    error_lower = error.lower()
    
    suggestions = []
    
    if "not found" in error_lower or "does not exist" in error_lower:
        suggestions.append("🔍 Use `get_database_schema()` to see available tables")
        suggestions.append("📋 Table names are case-sensitive in BigQuery")
    
    if "column" in error_lower:
        suggestions.append("🔍 Use `get_table_info('table_name')` to see column names")
        suggestions.append("📝 Column names follow OMOP CDM conventions")
    
    if "syntax" in error_lower:
        suggestions.append("📝 Check SQL syntax - BigQuery uses Standard SQL")
        suggestions.append("💡 Try a simpler query first: `SELECT * FROM table LIMIT 5`")
    
    if "permission" in error_lower or "access" in error_lower:
        suggestions.append("🔐 Ensure your GCP credentials are configured correctly")
        suggestions.append("📧 Contact datathon organizers if access issues persist")
    
    if not suggestions:
        suggestions.append("🔍 Use `get_database_schema()` to explore available data")
        suggestions.append("📋 Use `get_table_info('table_name')` to understand table structure")
    
    suggestion_text = "\n".join(f"   {s}" for s in suggestions)
    
    return f"""❌ **Query Failed:** {error}

🛠️ **How to fix this:**
{suggestion_text}

🎯 **Quick Recovery Steps:**
1. `get_database_schema()` ← See what tables exist
2. `get_table_info('your_table')` ← Check exact column names
3. Retry your query with correct names

📚 **Database:** {DATABASE_NAME} (OMOP CDM format)"""


# ==========================================
# MCP TOOLS - PUBLIC API
# ==========================================

@mcp.tool()
def get_database_schema() -> str:
    """🔍 Discover what data is available in AmsterdamUMCdb.

    **When to use:** Start here to understand what tables exist and what data you can query.

    **What this does:** Queries BigQuery to show ALL tables that actually exist in the dataset.

    **Next steps after using this:**
    - Use `get_table_info(table_name)` to explore a specific table's structure
    - Common starting points: `person` (demographics), `measurement` (clinical observations), `observation` (procedures/devices), `device_exposure` (medical devices)

    **Important (to avoid tool loops):**
    - If you already called `get_database_schema()` in this conversation, do NOT call it again.
      Proceed to `get_table_info(...)` or a query/search instead.

    **Privacy Note:** All data is de-identified. Patient IDs are synthetic.

    Returns:
        List of available tables with descriptions
    """
    banner = _get_status_banner()
    
    try:
        # Query BigQuery to get ACTUAL tables in the dataset
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        
        schema_query = f"""
        SELECT table_name 
        FROM `{dataset_project}`.`{config['dataset']}`.INFORMATION_SCHEMA.TABLES
        WHERE table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        
        from google.cloud import bigquery
        client = bigquery.Client(project=config["project"], location=config.get("location", "EU"))
        result = client.query(schema_query, location=config.get("location", "EU")).result()
        
        actual_tables = [row.table_name for row in result]
        
        # Build simple table list - no hardcoded descriptions
        table_list = []
        for table_name in actual_tables:
            # Optional: add description if we have it in config, but don't require it
            if table_name in UMCDB_TABLES:
                table_list.append(f"📋 **{table_name}** - {UMCDB_TABLES[table_name]['description']}")
            else:
                table_list.append(f"📋 **{table_name}**")
        
        tables_text = "\n".join(table_list)
        
        return f"""{banner}
📊 **Available Tables in Dataset ({len(actual_tables)} tables):**

{tables_text}
💡 **Next:** Pick ONE relevant table and call `get_table_info('table_name', show_sample=false)`.
🧠 **Avoid loops:** Do not call `get_database_schema()` again in this conversation unless the dataset config changed.

🔒 **Privacy:** All data is de-identified. Use aggregated queries for analysis."""
    
    except Exception as e:
        # Fallback to static list if query fails
        logger.error(f"Failed to query schema: {e}")
        table_list = []
        for table_name, info in UMCDB_TABLES.items():
            table_list.append(f"📋 **{table_name}**")
            table_list.append(f"   {info['description']}")
        tables_text = "\n".join(table_list)
        
        return f"""{banner}
📊 **Available Tables (fallback list):**

{tables_text}
⚠️ Could not query live schema. Use `get_table_info('table_name')` to verify table exists."""


@mcp.tool()
def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """📋 Explore a specific table's structure and see sample data.

    **When to use:** After identifying a table of interest from `get_database_schema()`.

    **What this does:**
    - Shows all columns with their data types
    - Optionally displays sample rows to understand data format
    - Provides the EXACT table path to use in queries

    **Pro tip:** Always look at sample data to understand actual values and formats.

    Args:
        table_name: Table name from get_database_schema() (e.g., 'person', 'measurement', 'observation')
        show_sample: Whether to include sample rows (default: True, recommended)

    Returns:
        Complete table structure with sample data

    **Privacy Note:** Sample data shows de-identified records only.
    """
    # Get optional description from config (if available)
    info = get_table_info_config(table_name.lower()) if table_name.lower() in UMCDB_TABLES else None

    banner = _get_status_banner()
    
    try:
        full_table_path = get_bigquery_table_path(table_name.lower())
        
        # Get column information from BigQuery
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        
        # Note: INFORMATION_SCHEMA must use the backtick-per-component format
        schema_query = f"""
        SELECT column_name, data_type, is_nullable
        FROM `{dataset_project}`.`{config['dataset']}`.INFORMATION_SCHEMA.COLUMNS
        WHERE table_name = '{table_name.lower()}'
        ORDER BY ordinal_position
        LIMIT 100
        """
        
        # Security check for schema query
        is_safe, msg, _ = enforce_security(schema_query)
        if not is_safe:
            # Fallback - show minimal info if schema query fails
            desc = info['description'] if info else "OMOP CDM table"
            result = f"""{banner}
📋 **Table:** {full_table_path}

{desc}

**To query this table, use:** {full_table_path}

⚠️ Could not fetch live schema: {msg}"""
            return result
        
        # Execute schema query
        schema_result = _execute_bigquery_query(schema_query)
        
        # Build result with optional description
        desc = info['description'] if info else "OMOP CDM table"
        notes = info.get('notes', '') if info else ''
        
        result = f"""{banner}
📋 **Table:** {full_table_path}

{desc}

**⚠️ IMPORTANT: When writing SQL queries, use this EXACT table path:**
{full_table_path}

**Column Information:**
{schema_result}
"""
        
        if notes:
            result += f"\n**Notes:** {notes}\n"
        
        if show_sample:
            sample_query = f"SELECT * FROM {full_table_path} LIMIT 3"
            sample_result = _execute_bigquery_query(sample_query)
            result += f"""
📊 **Sample Data (3 rows):**
{sample_result}

⚠️ **Privacy Note:** Sample data is de-identified. IDs are synthetic."""
        
        return result
    
    except Exception as e:
        error_msg = sanitize_error_for_user(str(e))
        desc = info['description'] if info else "Table information unavailable"
        return f"""❌ **Error:** {error_msg}

📋 **Table:** {table_name}
{desc}

💡 Use `get_database_schema()` to see all available tables."""


@mcp.tool()
def execute_umcdb_query(sql_query: str) -> str:
    """🚀 Execute SQL queries to analyze AmsterdamUMCdb data.

    **💡 Pro tip:** For best results, explore the database structure first!

    **Recommended workflow:**
    1. **See available tables:** Use `get_database_schema()` to list all tables
    2. **Examine table structure:** Use `get_table_info('table_name')` to see columns and get the FULL table path
    3. **Write your SQL query:** Use the EXACT full table path from `get_table_info()` output

    **CRITICAL: Use the FULL table path (copy exactly from get_table_info output):**
    ✅ CORRECT: SELECT * FROM `amsterdamumcdb`.`van_gogh_2026_datathon`.`person` LIMIT 10
    ✅ CORRECT: SELECT COUNT(DISTINCT person_id) FROM `amsterdamumcdb`.`van_gogh_2026_datathon`.`observation` WHERE observation_concept_id = 4128124 GROUP BY observation_concept_id LIMIT 10
    ❌ WRONG: SELECT * FROM person LIMIT 10 (missing project.dataset prefix)

    **IMPORTANT REQUIREMENTS:**
    - All queries MUST include a LIMIT clause (max 1000 rows)
    - Use aggregated queries (COUNT, AVG, etc.) for statistical analysis
    - Direct patient lookups are blocked for privacy protection

    **Security:**
    - Queries are validated for SQL injection and re-identification risks
    - Rate limiting is enforced to prevent data extraction
    - Query metadata is logged (not results) for compliance

    Args:
        sql_query: Your SQL SELECT query with FULL table paths (must include LIMIT clause)

    Returns:
        Query results or helpful error messages with next steps
    """
    return _execute_bigquery_query(sql_query)


@mcp.tool()
def get_patient_demographics(limit: int = 100) -> str:
    """👥 Get aggregated patient demographics from AmsterdamUMCdb.

    **What this does:** Returns aggregated demographic statistics.
    Individual patient records are not returned for privacy protection.

    **Privacy-safe:** Returns only aggregated counts, not individual records.

    Args:
        limit: Maximum number of demographic groups to return (default: 100, max: 1000)

    Returns:
        Aggregated demographic statistics
    """
    if not _validate_limit(limit):
        return f"Error: Invalid limit. Must be between 1 and {MAX_QUERY_ROWS}."
    
    config = get_bigquery_config()
    table_path = f"`{config['project']}.{config['dataset']}.person`"
    
    query = f"""
    SELECT 
        gender_concept_id,
        COUNT(*) as patient_count,
        AVG(EXTRACT(YEAR FROM CURRENT_DATE()) - year_of_birth) as avg_age
    FROM {table_path}
    GROUP BY gender_concept_id
    HAVING COUNT(*) >= 5
    ORDER BY patient_count DESC
    LIMIT {limit}
    """
    
    result = _execute_bigquery_query(query)
    
    return f"""👥 **Patient Demographics (Aggregated)**

{result}

📊 **Notes:**
- Groups with fewer than 5 patients are suppressed for privacy
- Ages are approximate (based on year of birth)
- Gender concept IDs follow OMOP CDM standards"""


@mcp.tool()
def get_measurement_statistics(
    measurement_concept_id: int | None = None,
    limit: int = 50
) -> str:
    """📈 Get statistics for clinical measurements.

    **What this does:** Returns aggregated statistics for clinical measurements
    (vital signs, lab values, etc.) from the ICU data.

    **Privacy-safe:** Returns only aggregated statistics.

    Args:
        measurement_concept_id: Optional OMOP concept ID to filter by specific measurement
        limit: Maximum number of measurement types to return (default: 50)

    Returns:
        Aggregated measurement statistics

    **Example:** Get statistics for a specific measurement:
    `get_measurement_statistics(measurement_concept_id=3004249)` # Systolic BP
    """
    if not _validate_limit(limit):
        return f"Error: Invalid limit. Must be between 1 and {MAX_QUERY_ROWS}."
    
    config = get_bigquery_config()
    table_path = f"`{config['project']}.{config['dataset']}.measurement`"
    
    where_clause = ""
    if measurement_concept_id:
        where_clause = f"WHERE measurement_concept_id = {measurement_concept_id}"
    
    query = f"""
    SELECT 
        measurement_concept_id,
        COUNT(*) as n_observations,
        AVG(value_as_number) as mean_value,
        STDDEV(value_as_number) as std_value,
        MIN(value_as_number) as min_value,
        MAX(value_as_number) as max_value,
        APPROX_QUANTILES(value_as_number, 2)[OFFSET(1)] as median_value
    FROM {table_path}
    {where_clause}
    GROUP BY measurement_concept_id
    HAVING COUNT(*) >= 10
    ORDER BY n_observations DESC
    LIMIT {limit}
    """
    
    result = _execute_bigquery_query(query)
    
    return f"""📈 **Measurement Statistics**

{result}

📊 **Notes:**
- Only measurements with 10+ observations are shown
- Values are aggregated across all patients
- Use OMOP Athena to look up concept_id meanings"""


@mcp.tool()
def get_drug_exposure_summary(limit: int = 50) -> str:
    """💊 Get summary of drug exposures in AmsterdamUMCdb.

    **What this does:** Returns aggregated statistics on medication usage
    in the ICU, including frequency and duration patterns.

    **Privacy-safe:** Returns only aggregated counts.

    Args:
        limit: Maximum number of drugs to return (default: 50)

    Returns:
        Aggregated drug exposure statistics
    """
    if not _validate_limit(limit):
        return f"Error: Invalid limit. Must be between 1 and {MAX_QUERY_ROWS}."
    
    config = get_bigquery_config()
    table_path = f"`{config['project']}.{config['dataset']}.drug_exposure`"
    
    query = f"""
    SELECT 
        drug_concept_id,
        COUNT(*) as n_exposures,
        COUNT(DISTINCT person_id) as n_patients,
        AVG(TIMESTAMP_DIFF(drug_exposure_end_datetime, drug_exposure_start_datetime, HOUR)) as avg_duration_hours
    FROM {table_path}
    GROUP BY drug_concept_id
    HAVING COUNT(DISTINCT person_id) >= 5
    ORDER BY n_exposures DESC
    LIMIT {limit}
    """
    
    result = _execute_bigquery_query(query)
    
    return f"""💊 **Drug Exposure Summary**

{result}

📊 **Notes:**
- Only drugs given to 5+ patients are shown
- Duration calculated from start to end datetime
- Use OMOP Athena to look up drug concept names"""


@mcp.tool()
def get_condition_prevalence(limit: int = 50) -> str:
    """🏥 Get prevalence of diagnoses/conditions in AmsterdamUMCdb.

    **What this does:** Returns aggregated counts of diagnoses and
    clinical conditions recorded in the ICU.

    **Privacy-safe:** Returns only aggregated counts.

    Args:
        limit: Maximum number of conditions to return (default: 50)

    Returns:
        Aggregated condition prevalence statistics
    """
    if not _validate_limit(limit):
        return f"Error: Invalid limit. Must be between 1 and {MAX_QUERY_ROWS}."
    
    config = get_bigquery_config()
    table_path = f"`{config['project']}.{config['dataset']}.condition_occurrence`"
    
    query = f"""
    SELECT 
        condition_concept_id,
        COUNT(*) as n_occurrences,
        COUNT(DISTINCT person_id) as n_patients
    FROM {table_path}
    GROUP BY condition_concept_id
    HAVING COUNT(DISTINCT person_id) >= 5
    ORDER BY n_patients DESC
    LIMIT {limit}
    """
    
    result = _execute_bigquery_query(query)
    
    return f"""🏥 **Condition Prevalence**

{result}

📊 **Notes:**
- Only conditions affecting 5+ patients are shown
- Conditions are coded using OMOP concept IDs
- Use OMOP Athena to look up condition names"""


@mcp.tool()
def get_mortality_statistics() -> str:
    """📊 Get aggregated mortality statistics from AmsterdamUMCdb.

    **What this does:** Returns aggregated mortality statistics
    for ICU patients, broken down by relevant factors.

    **Privacy-safe:** Returns only aggregated statistics.

    Returns:
        Aggregated mortality statistics
    """
    config = get_bigquery_config()
    death_table = f"`{config['project']}.{config['dataset']}.death`"
    person_table = f"`{config['project']}.{config['dataset']}.person`"
    
    query = f"""
    WITH mortality AS (
        SELECT 
            p.person_id,
            p.gender_concept_id,
            CASE 
                WHEN d.person_id IS NOT NULL THEN 1 
                ELSE 0 
            END as died
        FROM {person_table} p
        LEFT JOIN {death_table} d ON p.person_id = d.person_id
    )
    SELECT 
        gender_concept_id,
        COUNT(*) as total_patients,
        SUM(died) as deaths,
        ROUND(100.0 * SUM(died) / COUNT(*), 2) as mortality_rate_pct
    FROM mortality
    GROUP BY gender_concept_id
    HAVING COUNT(*) >= 10
    ORDER BY total_patients DESC
    LIMIT 100
    """
    
    result = _execute_bigquery_query(query)
    
    return f"""📊 **Mortality Statistics**

{result}

📊 **Notes:**
- Mortality rates are aggregated by gender
- Only groups with 10+ patients are shown
- Gender concept IDs follow OMOP CDM standards"""


@mcp.tool()
def get_security_info() -> str:
    """🔒 Get current security and compliance status.

    **What this does:** Shows current security settings, rate limits,
    and EULA compliance status.

    **Why this matters:** Ensures you understand the privacy protections
    in place and your current usage within limits.

    Returns:
        Security and compliance status information
    """
    status = get_security_status()
    datathon_status = get_datathon_period_status()
    
    rate_info = status["rate_limiter"]
    audit_info = status["audit_log"]
    
    return f"""🔒 **TULIP Security Status**

📅 **Datathon Period:**
{datathon_status}

⏱️ **Rate Limiting:**
- Queries in last hour: {rate_info['queries_in_last_hour']} / {rate_info['max_per_hour']}
- Max per minute: {rate_info['max_per_minute']}

📝 **Session Statistics:**
- Total queries: {audit_info['total_queries']}
- Successful: {audit_info.get('successful', 0)}
- Blocked: {audit_info.get('failed', 0)}

🛡️ **Security Features Active:**
- ✅ SQL injection protection
- ✅ Re-identification attack prevention
- ✅ Rate limiting
- ✅ Query audit logging (metadata only)
- ✅ Result privacy checks
- ✅ K-anonymity enforcement (min group size: 5)

📋 **EULA Compliance:**
- BigQuery-only access (no local data storage)
- All queries logged for accountability
- Code available at: github.com/[your-repo]/TULIP"""


# ==========================================
# OMOP VOCABULARY TOOLS
# NOTE: Van Gogh dataset only includes clinical tables, not vocabulary tables
# These tools require concept tables which may not be available
# ==========================================

@mcp.tool()
def search_by_source_text(
    table: str,
    search_term: str,
    source_column: str | None = None,
    additional_filters: str | None = None,
    limit: int = 100
) -> str:
    """🔍 Search clinical data using original text values (works without relying on OMOP vocabulary tables).

    **When to use:** Find procedures, conditions, drugs, or measurements by searching their 
    original text descriptions (not OMOP concept IDs).

    **Examples:**
    - search_by_source_text("device_exposure", "ECMO")
    - search_by_source_text("observation", "ECMO")
    - search_by_source_text("condition_occurrence", "sepsis")
    - search_by_source_text("drug_exposure", "aspirin")
    - search_by_source_text("measurement", "heart rate")

    Args:
        table: Table to search (use `get_database_schema()` to see what exists)
        search_term: Text to search for in a *_source_value column
        source_column: Optional override of the source text column (e.g., "device_source_value")
        additional_filters: Optional SQL WHERE conditions
        limit: Maximum rows (default: 100, max: 500)

    Returns:
        Aggregated results with source values and counts
    """
    banner = _get_status_banner()

    table = table.strip()
    if not table:
        return f"{banner}\n❌ Table name is required."
    
    if limit > 500:
        limit = 500
    
    try:
        from google.cloud import bigquery

        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        dataset = config["dataset"]
        location = config.get("location", "EU")

        # Resolve full table path in BigQuery (project/dataset/table)
        full_table_path = get_bigquery_table_path(table.lower())

        # If caller didn't specify the source column, auto-detect the best *_source_value column
        if not source_column:
            cols_query = f"""
            SELECT column_name
            FROM `{dataset_project}`.`{dataset}`.INFORMATION_SCHEMA.COLUMNS
            WHERE table_name = '{table.lower()}'
              AND LOWER(column_name) LIKE '%_source_value'
            ORDER BY column_name
            LIMIT 50
            """

            job_config = bigquery.QueryJobConfig()
            cols_result = _bq_client.query(cols_query, job_config=job_config, location=location).result()
            source_cols = [row.column_name for row in cols_result]

            if not source_cols:
                # Helpful fallback: show columns so user/LLM can choose explicitly
                all_cols_query = f"""
                SELECT column_name
                FROM `{dataset_project}`.`{dataset}`.INFORMATION_SCHEMA.COLUMNS
                WHERE table_name = '{table.lower()}'
                ORDER BY ordinal_position
                LIMIT 100
                """
                all_cols_result = _bq_client.query(all_cols_query, job_config=job_config, location=location).result()
                all_cols = [row.column_name for row in all_cols_result]
                return f"""{banner}
❌ No `*_source_value` column found for table **{table.lower()}**.

Try:
- Use `get_table_info("{table.lower()}")` and choose a text column manually
- Call `search_by_source_text(..., source_column="your_column")`

Columns (first {min(100, len(all_cols))}):
{", ".join(all_cols[:100])}"""

            # Heuristics to pick the most relevant source column
            table_l = table.lower()
            preferred = []
            preferred.append(f"{table_l}_source_value")  # rarely exists (but if it does, best)

            # Common OMOP pattern: first token before '_' + "_source_value"
            base = table_l.split("_", 1)[0] if "_" in table_l else table_l
            preferred.append(f"{base}_source_value")

            # Pick the first preferred that exists, else first *_source_value column
            source_column = next((c for c in preferred if c in source_cols), source_cols[0])

        # Escape search term for SQL LIKE
        safe_term = search_term.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
        
        # Build WHERE clause
        where_clause = f"LOWER(CAST(`{source_column}` AS STRING)) LIKE LOWER('%{safe_term}%')"
        
        if additional_filters:
            # Basic validation
            dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "--", ";"]
            if any(d.lower() in additional_filters.lower() for d in dangerous):
                return f"{banner}\n❌ Invalid filter: potentially dangerous SQL detected"
            where_clause += f" AND ({additional_filters})"
        
        # Aggregated query to respect privacy
        query = f"""
        SELECT 
            `{source_column}` AS source_value,
            COUNT(DISTINCT person_id) as patient_count,
            COUNT(*) as event_count
        FROM {full_table_path}
        WHERE {where_clause}
        GROUP BY source_value
        HAVING COUNT(DISTINCT person_id) >= 5
        ORDER BY patient_count DESC
        LIMIT {limit}
        """
        
        # Security check
        is_safe, msg, _ = enforce_security(query)
        if not is_safe:
            return f"{banner}\n❌ **Security Error:** {msg}"
        
        job_config = bigquery.QueryJobConfig()
        result = _bq_client.query(query, job_config=job_config, location=location).result()
        df = result.to_dataframe()
        
        if df.empty:
            return f"""{banner}
🔍 **Search: "{search_term}"** in `{table.lower()}`
Using:
- table: {full_table_path}
- column: `{source_column}`

No results found (or all matches were in groups < 5 patients due to privacy filtering).

Next (do NOT re-run `get_database_schema()`):
- Try broader terms (e.g., "tube", "vent", "ett", "endotrache")
- Try another table (often `observation` vs `measurement`)
- Or specify a different text column via `source_column=...` after `get_table_info(...)`"""
        
        # Format results
        total_patients = df['patient_count'].sum()
        total_events = df['event_count'].sum()
        
        result_text = []
        for _, row in df.head(20).iterrows():
            sv = row.get("source_value", "")
            sv = "" if sv is None else str(sv)
            result_text.append(
                f"| {sv[:50]} | {row['patient_count']} | {row['event_count']} |"
            )
        
        return f"""{banner}
🔍 **Search: "{search_term}"** in {table}

Found {len(df)} distinct values (showing top 20):

| Source Value | Patients | Events |
|-------------|----------|--------|
{chr(10).join(result_text)}

**Summary:**
- Total distinct patients: {total_patients}
- Total events: {total_events}
- Groups with ≥5 patients: {len(df)}

💡 Use these source values to refine your queries."""
        
    except Exception as e:
        logger.error(f"Source text search failed: {e}")
        return f"{banner}\n❌ Search failed: {str(e)}"


@mcp.tool()
def lookup_concept(concept_id: int) -> str:
    """🔍 Get the human-readable name for an OMOP concept ID.

    **When to use:** When you see a concept_id in query results and want to know what it means.

    **Examples:**
    - concept_id 8507 → "MALE"
    - concept_id 8532 → "FEMALE"

    Args:
        concept_id: The OMOP concept ID to look up

    Returns:
        Concept name, domain, and source description
    """
    banner = _get_status_banner()
    
    try:
        from tulip.config import lookup_concept_in_dictionary
        
        result = lookup_concept_in_dictionary(int(concept_id))
        
        if result is None:
            return f"{banner}\n❌ Concept ID {concept_id} not found in AmsterdamUMCdb dictionary."
        
        return f"""{banner}
🔍 **Concept Lookup: {concept_id}**

| Field | Value |
|-------|-------|
| **Name** | {result['concept_name']} |
| **Domain** | {result['domain_id']} |
| **Vocabulary** | {result['vocabulary_id'] or 'N/A'} |
| **Original Description** | {result['source_code_description'] or 'N/A'} |

💡 Use `search_concepts('{result['concept_name']}')` to find related concepts."""
        
    except Exception as e:
        logger.error(f"Concept lookup failed: {e}")
        return f"{banner}\n❌ Concept lookup failed: {str(e)}"


@mcp.tool()
def search_concepts(
    search_term: str,
    domain: str | None = None,
    limit: int = 20
) -> str:
    """🔎 Search for OMOP concepts by name using AmsterdamUMCdb dictionary.

    **When to use:** When you want to find the concept_id for a condition, drug, measurement, etc.

    **Examples:**
    - search_concepts("male") → Find gender concepts
    - search_concepts("ECMO", domain="Procedure") → Find ECMO procedure concepts
    - search_concepts("sepsis", domain="Condition") → Find sepsis-related concepts

    Args:
        search_term: Text to search for (searches concept names and source descriptions)
        domain: Optional filter by domain (Gender, Visit, Procedure, Condition, Drug, Measurement, etc.)
        limit: Maximum results to return (default: 20, max: 50)

    Returns:
        List of matching concepts with IDs, names, and domains
    """
    banner = _get_status_banner()
    
    if limit > 50:
        limit = 50
    
    try:
        from tulip.config import search_concepts_in_dictionary
        
        results = search_concepts_in_dictionary(search_term, domain, limit)
        
        if not results:
            return f"""{banner}
🔎 **Search: "{search_term}"** {f'(domain: {domain})' if domain else ''}

No matching concepts found in AmsterdamUMCdb dictionary. Try:
- Different spelling
- More general term
- Remove domain filter
- Check available domains: Gender, Visit, Procedure, Condition, Drug, Measurement"""
        
        results_text = []
        for r in results:
            cid = r['concept_id'] if r['concept_id'] else 'UNMAPPED'
            name = r['concept_name'][:40] if r['concept_name'] else 'N/A'
            domain = r['domain_id'][:15] if r['domain_id'] else 'Unknown'
            source = r['source_code_description'][:40] if r['source_code_description'] else ''
            
            results_text.append(
                f"| {cid} | {name} | {domain} | {source} |"
            )
        
        return f"""{banner}
🔎 **Search: "{search_term}"** {f'(domain: {domain})' if domain else ''}

Found {len(results)} concepts:

| ID | Name | Domain | Source Description |
|----|------|--------|-------------------|
{chr(10).join(results_text)}

💡 Mapped concepts have numeric IDs - use these in queries.
💡 UNMAPPED concepts exist in source data but have no standard ID."""
        
    except Exception as e:
        logger.error(f"Concept search failed: {e}")
        return f"{banner}\n❌ Concept search failed: {str(e)}"


# ==========================================
# SERVER INITIALIZATION
# ==========================================

def _initialize_server():
    """Initialize the MCP server and BigQuery connection."""
    try:
        _init_bigquery()
        logger.info(f"🌷 {FULL_NAME} ({APP_NAME.upper()}) initialized")
        logger.info(f"📊 Database: {DATABASE_NAME}")
        logger.info(f"🎨 Datathon: {DATATHON_NAME}")
        logger.info(get_datathon_period_status())
    except Exception as e:
        logger.error(f"Server initialization failed: {e}")
        raise


def main():
    """Main entry point for MCP server.

    Runs FastMCP server in STDIO mode for local LLM clients (e.g., LMStudio).

    Environment Variables:
        TULIP_BQ_PROJECT: Google Cloud project ID (required)
        TULIP_BQ_DATASET: BigQuery dataset name (required)
        MCP_TRANSPORT: "stdio" (default) or "http"
        MCP_HOST: Host for HTTP mode (default: "localhost")
        MCP_PORT: Port for HTTP mode (default: 3000)
    """
    # Initialize server
    _initialize_server()
    
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    
    if transport in ("sse", "http"):
        host = os.getenv("MCP_HOST", "localhost")  # Default to localhost for security
        port = int(os.getenv("MCP_PORT", "3000"))
        path = os.getenv("MCP_PATH", "/sse")
        
        logger.warning("⚠️ HTTP transport enabled - ensure proper network security!")
        mcp.run(transport="streamable-http", host=host, port=port, path=path)
    else:
        # Default: STDIO for local LLM usage
        logger.info("Starting in STDIO mode for local LLM integration")
        mcp.run()


if __name__ == "__main__":
    main()

