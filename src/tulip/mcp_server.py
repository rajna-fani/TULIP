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

    **What this does:** Shows all 7 OMOP CDM tables available in the database with descriptions.

    **Next steps after using this:**
    - Use `get_table_info(table_name)` to explore a specific table's structure
    - Common starting points: `person` (demographics), `measurement` (clinical observations)

    **Privacy Note:** All data is de-identified. Patient IDs are synthetic.

    Returns:
        List of available tables with descriptions
    """
    banner = _get_status_banner()
    
    table_list = []
    for table_name, info in UMCDB_TABLES.items():
        table_list.append(f"📋 **{table_name}**")
        table_list.append(f"   {info['description']}")
        if 'omop_docs' in info:
            table_list.append(f"   📚 OMOP CDM: {info['omop_docs']}")
        table_list.append("")
    
    tables_text = "\n".join(table_list)
    
    return f"""{banner}
📊 **Available Tables (OMOP CDM Format):**

{tables_text}
💡 **Tip:** Use `get_table_info('table_name')` to see full column details and sample data.

🔒 **Privacy:** All data is de-identified. Use aggregated queries for analysis."""


@mcp.tool()
def get_table_info(table_name: str, show_sample: bool = True) -> str:
    """📋 Explore a specific table's structure and see sample data.

    **When to use:** After identifying a table of interest from `get_database_schema()`.

    **What this does:**
    - Shows all columns with their data types
    - Optionally displays sample rows to understand data format
    - Provides OMOP CDM documentation links

    **Pro tip:** Always look at sample data to understand actual values and formats.

    Args:
        table_name: Table name (e.g., 'person', 'measurement', 'drug_exposure')
        show_sample: Whether to include sample rows (default: True, recommended)

    Returns:
        Complete table structure with sample data

    **Privacy Note:** Sample data shows de-identified records only.
    """
    # Get static info
    info = get_table_info_config(table_name.lower())
    if not info:
        available = ", ".join(UMCDB_TABLES.keys())
        return f"""❌ **Table Not Found:** '{table_name}'

📋 **Available tables:** {available}

💡 Use `get_database_schema()` to see all tables with descriptions."""

    banner = _get_status_banner()
    
    try:
        full_table_path = get_bigquery_table_path(table_name.lower())
        
        # Get column information from BigQuery
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        schema_query = f"""
        SELECT column_name, data_type, is_nullable
        FROM `{dataset_project}.{config['dataset']}.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = '{table_name.lower()}'
        ORDER BY ordinal_position
        """
        
        # Security check for schema query
        is_safe, msg, _ = enforce_security(schema_query + " LIMIT 100")
        if not is_safe:
            # Fallback to static info
            result = f"""{banner}
📋 **Table:** {table_name}

{info['description']}

**Key Columns:** {', '.join(info['key_columns'])}

**Notes:** {info['notes']}

⚠️ Could not fetch live schema: {msg}"""
            return result
        
        # Execute schema query
        schema_result = _execute_bigquery_query(schema_query + " LIMIT 100")
        
        result = f"""{banner}
📋 **Table:** {full_table_path}

{info['description']}

**Column Information:**
{schema_result}

**Notes:** {info['notes']}
"""
        
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
        return f"""❌ **Error:** {error_msg}

📋 **Static Table Info:**
Table: {table_name}
Description: {info['description']}
Key columns: {', '.join(info['key_columns'])}"""


@mcp.tool()
def execute_umcdb_query(sql_query: str) -> str:
    """🚀 Execute SQL queries to analyze AmsterdamUMCdb data.

    **💡 Pro tip:** For best results, explore the database structure first!

    **Recommended workflow:**
    1. **See available tables:** Use `get_database_schema()` to list all tables
    2. **Examine table structure:** Use `get_table_info('table_name')` to see columns
    3. **Write your SQL query:** Use exact table/column names from exploration

    **IMPORTANT REQUIREMENTS:**
    - All queries MUST include a LIMIT clause (max 1000 rows)
    - Use aggregated queries (COUNT, AVG, etc.) for statistical analysis
    - Direct patient lookups are blocked for privacy protection

    **Security:**
    - Queries are validated for SQL injection and re-identification risks
    - Rate limiting is enforced to prevent data extraction
    - Query metadata is logged (not results) for compliance

    Args:
        sql_query: Your SQL SELECT query (must include LIMIT clause)

    Returns:
        Query results or helpful error messages with next steps

    **Example queries:**
    - `SELECT gender_concept_id, COUNT(*) as n FROM person GROUP BY gender_concept_id LIMIT 10`
    - `SELECT measurement_concept_id, AVG(value_as_number) FROM measurement GROUP BY 1 LIMIT 20`
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
# ==========================================

@mcp.tool()
def lookup_concept(concept_id: int) -> str:
    """🔍 Get the human-readable name for an OMOP concept ID.

    **When to use:** When you see a concept_id in query results and want to know what it means.

    **Examples:**
    - concept_id 8507 → "Male"
    - concept_id 8532 → "Female"
    - concept_id 4329847 → "Sepsis"

    Args:
        concept_id: The OMOP concept ID to look up

    Returns:
        Concept name, domain, and vocabulary information
    """
    banner = _get_status_banner()
    
    try:
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        location = config.get("location", "EU")
        
        query = f"""
        SELECT 
            concept_id,
            concept_name,
            domain_id,
            vocabulary_id,
            concept_class_id,
            standard_concept
        FROM `{dataset_project}.{config['dataset']}.concept`
        WHERE concept_id = {int(concept_id)}
        """
        
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig()
        result = _bq_client.query(query, job_config=job_config, location=location).result()
        
        rows = list(result)
        if not rows:
            return f"{banner}\n❌ Concept ID {concept_id} not found in vocabulary."
        
        row = rows[0]
        return f"""{banner}
🔍 **Concept Lookup: {concept_id}**

| Field | Value |
|-------|-------|
| **Name** | {row.concept_name} |
| **Domain** | {row.domain_id} |
| **Vocabulary** | {row.vocabulary_id} |
| **Class** | {row.concept_class_id} |
| **Standard** | {'Yes' if row.standard_concept == 'S' else 'No'} |

💡 Use `search_concepts('{row.concept_name}')` to find related concepts."""
        
    except Exception as e:
        logger.error(f"Concept lookup failed: {e}")
        return f"{banner}\n❌ Concept lookup failed: {str(e)}"


@mcp.tool()
def search_concepts(
    search_term: str,
    domain: str | None = None,
    limit: int = 20
) -> str:
    """🔎 Search for OMOP concepts by name.

    **When to use:** When you want to find the concept_id for a condition, drug, measurement, etc.

    **Examples:**
    - search_concepts("sepsis") → Find sepsis-related concepts
    - search_concepts("aspirin", domain="Drug") → Find aspirin drug concepts
    - search_concepts("heart rate", domain="Measurement") → Find heart rate measurements

    Args:
        search_term: Text to search for (searches concept names and synonyms)
        domain: Optional filter by domain (Drug, Condition, Measurement, Procedure, etc.)
        limit: Maximum results to return (default: 20, max: 50)

    Returns:
        List of matching concepts with IDs, names, and domains
    """
    banner = _get_status_banner()
    
    if limit > 50:
        limit = 50
    
    try:
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        location = config.get("location", "EU")
        
        # Escape search term for SQL
        safe_term = search_term.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
        
        domain_filter = ""
        if domain:
            safe_domain = domain.replace("'", "''")
            domain_filter = f"AND domain_id = '{safe_domain}'"
        
        query = f"""
        SELECT DISTINCT
            c.concept_id,
            c.concept_name,
            c.domain_id,
            c.vocabulary_id,
            c.concept_class_id,
            c.standard_concept
        FROM `{dataset_project}.{config['dataset']}.concept` c
        LEFT JOIN `{dataset_project}.{config['dataset']}.concept_synonym` cs
            ON c.concept_id = cs.concept_id
        WHERE (
            LOWER(c.concept_name) LIKE LOWER('%{safe_term}%')
            OR LOWER(cs.concept_synonym_name) LIKE LOWER('%{safe_term}%')
        )
        {domain_filter}
        AND c.standard_concept = 'S'
        ORDER BY 
            CASE WHEN LOWER(c.concept_name) = LOWER('{safe_term}') THEN 0 ELSE 1 END,
            LENGTH(c.concept_name)
        LIMIT {limit}
        """
        
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig()
        result = _bq_client.query(query, job_config=job_config, location=location).result()
        
        rows = list(result)
        if not rows:
            return f"""{banner}
🔎 **Search: "{search_term}"** {f'(domain: {domain})' if domain else ''}

No matching concepts found. Try:
- Different spelling
- More general term
- Remove domain filter"""
        
        results_text = []
        for row in rows:
            std = "✓" if row.standard_concept == 'S' else ""
            results_text.append(
                f"| {row.concept_id} | {row.concept_name[:40]} | {row.domain_id} | {row.vocabulary_id} | {std} |"
            )
        
        return f"""{banner}
🔎 **Search: "{search_term}"** {f'(domain: {domain})' if domain else ''}

Found {len(rows)} concepts:

| ID | Name | Domain | Vocabulary | Std |
|----|------|--------|------------|-----|
{chr(10).join(results_text)}

💡 Use `lookup_concept(concept_id)` for full details.
💡 Use `get_concept_descendants(concept_id)` to find related concepts."""
        
    except Exception as e:
        logger.error(f"Concept search failed: {e}")
        return f"{banner}\n❌ Concept search failed: {str(e)}"


@mcp.tool()
def get_concept_descendants(
    concept_id: int,
    max_separation: int = 1,
    limit: int = 50
) -> str:
    """🌳 Find all descendant concepts of a parent concept.

    **When to use:** When you want to find all specific concepts under a general category.

    **Examples:**
    - get_concept_descendants(sepsis_concept_id) → Find all types of sepsis
    - get_concept_descendants(antibiotic_class_id) → Find all antibiotics in that class

    Args:
        concept_id: The parent concept ID
        max_separation: Maximum hierarchy levels to descend (default: 1, max: 3)
        limit: Maximum results (default: 50, max: 100)

    Returns:
        List of descendant concepts with their hierarchy level
    """
    banner = _get_status_banner()
    
    if max_separation > 3:
        max_separation = 3
    if limit > 100:
        limit = 100
    
    try:
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        location = config.get("location", "EU")
        
        # First get the parent concept name
        parent_query = f"""
        SELECT concept_name, domain_id
        FROM `{dataset_project}.{config['dataset']}.concept`
        WHERE concept_id = {int(concept_id)}
        """
        
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig()
        parent_result = _bq_client.query(parent_query, job_config=job_config, location=location).result()
        parent_rows = list(parent_result)
        
        if not parent_rows:
            return f"{banner}\n❌ Concept ID {concept_id} not found."
        
        parent_name = parent_rows[0].concept_name
        parent_domain = parent_rows[0].domain_id
        
        # Get descendants
        query = f"""
        SELECT 
            c.concept_id,
            c.concept_name,
            c.domain_id,
            ca.min_levels_of_separation as hierarchy_level
        FROM `{dataset_project}.{config['dataset']}.concept_ancestor` ca
        JOIN `{dataset_project}.{config['dataset']}.concept` c
            ON ca.descendant_concept_id = c.concept_id
        WHERE ca.ancestor_concept_id = {int(concept_id)}
            AND ca.min_levels_of_separation > 0
            AND ca.min_levels_of_separation <= {max_separation}
            AND c.standard_concept = 'S'
        ORDER BY ca.min_levels_of_separation, c.concept_name
        LIMIT {limit}
        """
        
        result = _bq_client.query(query, job_config=job_config, location=location).result()
        rows = list(result)
        
        if not rows:
            return f"""{banner}
🌳 **Descendants of: {parent_name}** (ID: {concept_id})

No descendant concepts found within {max_separation} level(s)."""
        
        results_text = []
        for row in rows:
            indent = "  " * row.hierarchy_level
            results_text.append(
                f"| {row.concept_id} | {indent}{row.concept_name[:35]} | {row.hierarchy_level} |"
            )
        
        return f"""{banner}
🌳 **Descendants of: {parent_name}** (ID: {concept_id}, Domain: {parent_domain})

Found {len(rows)} descendant concepts (max {max_separation} levels):

| ID | Name | Level |
|----|------|-------|
{chr(10).join(results_text)}

💡 Use these concept IDs in your queries to analyze specific conditions/drugs."""
        
    except Exception as e:
        logger.error(f"Get descendants failed: {e}")
        return f"{banner}\n❌ Get descendants failed: {str(e)}"


@mcp.tool()
def query_with_concepts(
    table: str,
    concept_column: str,
    concept_search: str,
    additional_filters: str | None = None,
    group_by: str | None = None,
    limit: int = 100
) -> str:
    """🚀 Query data using concept names instead of IDs.

    **When to use:** When you want to query clinical data using natural language concept names
    instead of numeric concept IDs.

    **Examples:**
    - query_with_concepts("condition_occurrence", "condition_concept_id", "sepsis")
    - query_with_concepts("drug_exposure", "drug_concept_id", "aspirin")
    - query_with_concepts("measurement", "measurement_concept_id", "heart rate")

    Args:
        table: Table to query (condition_occurrence, drug_exposure, measurement, etc.)
        concept_column: The concept ID column to filter on
        concept_search: Concept name to search for
        additional_filters: Optional SQL WHERE conditions (e.g., "value_as_number > 100")
        group_by: Optional GROUP BY columns
        limit: Maximum rows to return (default: 100)

    Returns:
        Query results with concept names included
    """
    banner = _get_status_banner()
    
    # Validate table
    valid_tables = ["condition_occurrence", "drug_exposure", "measurement", 
                    "procedure_occurrence", "visit_occurrence", "person"]
    if table.lower() not in valid_tables:
        return f"{banner}\n❌ Invalid table. Use one of: {', '.join(valid_tables)}"
    
    if limit > 500:
        limit = 500
    
    try:
        config = get_bigquery_config()
        dataset_project = config.get("dataset_project", config["project"])
        location = config.get("location", "EU")
        
        # First search for matching concepts
        safe_term = concept_search.replace("'", "''")
        
        concept_query = f"""
        SELECT concept_id, concept_name
        FROM `{dataset_project}.{config['dataset']}.concept`
        WHERE LOWER(concept_name) LIKE LOWER('%{safe_term}%')
            AND standard_concept = 'S'
        LIMIT 10
        """
        
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig()
        concept_result = _bq_client.query(concept_query, job_config=job_config, location=location).result()
        concept_rows = list(concept_result)
        
        if not concept_rows:
            return f"""{banner}
❌ No concepts found matching "{concept_search}".

Try:
- Different spelling
- More general term
- Use search_concepts() to explore available concepts"""
        
        # Get concept IDs
        concept_ids = [str(row.concept_id) for row in concept_rows]
        concept_names = {row.concept_id: row.concept_name for row in concept_rows}
        
        # Build the main query
        safe_concept_column = concept_column.replace("'", "''")
        
        where_clause = f"{safe_concept_column} IN ({','.join(concept_ids)})"
        if additional_filters:
            # Basic validation of additional filters
            dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "--", ";"]
            if any(d.lower() in additional_filters.lower() for d in dangerous):
                return f"{banner}\n❌ Invalid filter: potentially dangerous SQL detected"
            where_clause += f" AND ({additional_filters})"
        
        group_clause = ""
        select_clause = f"t.*, c.concept_name"
        if group_by:
            group_clause = f"GROUP BY {group_by}, c.concept_name"
            select_clause = f"{group_by}, c.concept_name, COUNT(*) as count"
        
        query = f"""
        SELECT {select_clause}
        FROM `{dataset_project}.{config['dataset']}.{table}` t
        JOIN `{dataset_project}.{config['dataset']}.concept` c
            ON t.{safe_concept_column} = c.concept_id
        WHERE {where_clause}
        {group_clause}
        LIMIT {limit}
        """
        
        # Security check
        is_safe, msg, _ = enforce_security(query)
        if not is_safe:
            return f"{banner}\n❌ **Security Error:** {msg}"
        
        result = _bq_client.query(query, job_config=job_config, location=location).result()
        df = result.to_dataframe()
        
        if df.empty:
            return f"""{banner}
🔎 **Query: {table}** where {concept_column} matches "{concept_search}"

No results found.

Matching concepts searched:
{chr(10).join([f'- {name} (ID: {cid})' for cid, name in concept_names.items()])}"""
        
        # Format results
        result_str = df.head(50).to_string(index=False)
        if len(df) > 50:
            result_str += f"\n... ({len(df)} total rows, showing first 50)"
        
        return f"""{banner}
🔎 **Query: {table}** where {concept_column} matches "{concept_search}"

Concepts matched:
{chr(10).join([f'- {name} (ID: {cid})' for cid, name in concept_names.items()])}

**Results ({len(df)} rows):**

{result_str}"""
        
    except Exception as e:
        logger.error(f"Query with concepts failed: {e}")
        return f"{banner}\n❌ Query failed: {str(e)}"


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

