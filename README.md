# 🌷 TULIP: Tool for UMCdb Language Interface and Processing

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![EULA Compliant](https://img.shields.io/badge/EULA-Compliant-green.svg)](#eula-compliance)

> **🎨 Van Gogh Datathon Edition**
> 
> A secure MCP (Model Context Protocol) server for querying AmsterdamUMCdb via **local LLMs only**.
> Designed for the ESICM Datathon with full EULA compliance.

## ⚠️ CRITICAL SECURITY NOTICE

**READ BEFORE USE:**

1. **LOCAL MODELS ONLY**: This tool is designed exclusively for use with local LLMs (e.g., LMStudio with gpt-oss-20b). **Never send queries or data to external APIs or cloud-based LLMs.**

2. **NO DATA EXPORT**: The AmsterdamUMCdb data must remain on Google BigQuery. Do not attempt to download, copy, or export any data.

3. **NO RE-IDENTIFICATION**: Any attempt to re-identify patients is strictly prohibited and blocked by this tool.

4. **CODE AVAILABILITY**: Per EULA requirements, all code must be made available to AmsterdamUMCdb administrators.

---

## 📋 Table of Contents

- [Overview](#overview)
- [EULA Compliance](#eula-compliance)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage with LMStudio](#usage-with-lmstudio)
- [Available MCP Tools](#available-mcp-tools)
- [Security Features](#security-features)
- [Privacy Best Practices](#privacy-best-practices)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

TULIP provides a secure interface for querying AmsterdamUMCdb through the Model Context Protocol (MCP), enabling local LLMs to help analyze ICU data while maintaining strict privacy and security controls.

### Key Features

- 🔒 **Security-First Design**: Multiple layers of protection against data leakage
- 🏥 **OMOP CDM Support**: Works with AmsterdamUMCdb's 7 OMOP tables
- 🤖 **Local LLM Integration**: Designed for LMStudio and gpt-oss-20b
- 📊 **Privacy-Preserving Queries**: Enforces aggregation and k-anonymity
- ⏱️ **Rate Limiting**: Prevents data extraction attempts
- 📝 **Audit Logging**: Tracks queries for compliance (without logging results)

### AmsterdamUMCdb Tables

AmsterdamUMCdb follows the [OMOP Common Data Model v5.4](https://ohdsi.github.io/CommonDataModel/cdm54.html) standard with 7 core tables:

| Table | Description | OMOP Docs |
|-------|-------------|-----------|
| `person` | Patient demographics (de-identified) | [person](https://ohdsi.github.io/CommonDataModel/cdm54.html#person) |
| `visit_occurrence` | ICU admission records | [visit_occurrence](https://ohdsi.github.io/CommonDataModel/cdm54.html#visit_occurrence) |
| `death` | Mortality records | [death](https://ohdsi.github.io/CommonDataModel/cdm54.html#death) |
| `condition_occurrence` | Diagnoses and conditions | [condition_occurrence](https://ohdsi.github.io/CommonDataModel/cdm54.html#condition_occurrence) |
| `drug_exposure` | Medication records | [drug_exposure](https://ohdsi.github.io/CommonDataModel/cdm54.html#drug_exposure) |
| `procedure_occurrence` | Clinical procedures | [procedure_occurrence](https://ohdsi.github.io/CommonDataModel/cdm54.html#procedure_occurrence) |
| `measurement` | ~1B clinical observations | [measurement](https://ohdsi.github.io/CommonDataModel/cdm54.html#measurement) |

**Note:** Use the `get_table_info('table_name')` MCP tool to see all columns and their data types (queried dynamically from BigQuery).

---

## EULA Compliance

TULIP is designed to comply with all terms of the AmsterdamUMCdb End User License Agreement:

| EULA Requirement | TULIP Implementation |
|------------------|---------------------|
| ✅ Only use via Google Cloud Platform | BigQuery-only access, no local storage |
| ✅ January-February 2026 only | Time-period enforcement in code |
| ✅ No downloading/copying | No data caching or export functionality |
| ✅ No sharing access | Per-user GCP authentication required |
| ✅ Non-commercial research only | Intended for datathon use |
| ✅ No re-identification attempts | Query validation blocks re-id patterns |
| ✅ Make code available | Open source on GitHub |
| ✅ Allow co-authorship | Contact info in README |

### Automatic EULA Protections

1. **Query Validation**: All queries are checked for re-identification risks
2. **Result Filtering**: Small groups (< 5 records) are suppressed
3. **Audit Trail**: Query metadata logged for accountability
4. **Rate Limiting**: 100 queries/hour, 10 queries/minute
5. **Row Limits**: Maximum 1000 rows per query

---

## Installation

### Prerequisites

1. **Python 3.10+**
2. **Google Cloud SDK** with authentication configured
3. **LMStudio** with a local model (e.g., gpt-oss-20b)
4. **Approved AmsterdamUMCdb access** (datathon registration)

### Install TULIP

```bash
# Clone the repository
git clone https://github.com/[your-username]/TULIP.git
cd TULIP

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

### Verify Installation

```bash
tulip --version
tulip status
```

---

## Configuration

### 1. Set BigQuery Credentials

```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Set project and dataset (provided by datathon organizers)
export TULIP_BQ_PROJECT="your-project-id"
export TULIP_BQ_DATASET="amsterdamumcdb"
```

### 2. Configure TULIP

```bash
# Interactive configuration
tulip config --project-id your-project-id --dataset amsterdamumcdb

# Verify configuration
tulip validate
```

### 3. Generate MCP Configuration

```bash
# For LMStudio
tulip mcp-config lmstudio

# Save to file
tulip mcp-config --output mcp_config.json
```

---

## Usage with LMStudio

### Step 1: Download a Local Model

1. Open LMStudio
2. Download a model (recommended: **gpt-oss-20b** or similar)
3. Load the model

### Step 2: Configure MCP Server

Add TULIP to your LMStudio MCP configuration:

```json
{
  "mcpServers": {
    "tulip": {
      "command": "python",
      "args": ["-m", "tulip.mcp_server"],
      "env": {
        "TULIP_BQ_PROJECT": "your-project-id",
        "TULIP_BQ_DATASET": "amsterdamumcdb"
      }
    }
  }
}
```

Or use uvx:

```json
{
  "mcpServers": {
    "tulip": {
      "command": "uvx",
      "args": ["tulip-mcp"],
      "env": {
        "TULIP_BQ_PROJECT": "your-project-id",
        "TULIP_BQ_DATASET": "amsterdamumcdb"
      }
    }
  }
}
```

### Step 3: Start Using

Ask your local LLM questions like:
- "What tables are available in AmsterdamUMCdb?"
- "Show me the patient demographics distribution"
- "What are the most common diagnoses in the ICU?"
- "Calculate the average length of stay by gender"

---

## Available MCP Tools

### 🔍 `get_database_schema()`
Discover available tables and their descriptions.

### 📋 `get_table_info(table_name, show_sample=True)`
Explore a specific table's structure and sample data.

### 🚀 `execute_umcdb_query(sql_query)`
Execute custom SQL queries (with security validation).

**Requirements:**
- Must include `LIMIT` clause (max 1000)
- Prefer aggregated queries
- Direct person_id lookups are blocked

### 👥 `get_patient_demographics(limit=100)`
Aggregated patient demographics statistics.

### 📈 `get_measurement_statistics(measurement_concept_id=None, limit=50)`
Statistics for clinical measurements (vitals, labs).

### 💊 `get_drug_exposure_summary(limit=50)`
Aggregated medication usage patterns.

### 🏥 `get_condition_prevalence(limit=50)`
Prevalence of diagnoses and conditions.

### 📊 `get_mortality_statistics()`
Aggregated mortality statistics by demographic factors.

### 🔒 `get_security_info()`
Current security status and rate limiting info.

---

## Security Features

### SQL Injection Protection
- Query parsing and validation
- Blocks multiple statements
- Rejects dangerous patterns

### Re-identification Prevention
```python
# BLOCKED: Direct patient lookup
SELECT * FROM person WHERE person_id = 12345

# BLOCKED: Finding unique records
SELECT * FROM person HAVING COUNT(*) = 1

# BLOCKED: Extreme value attacks
SELECT MIN(year_of_birth) FROM person

# ALLOWED: Aggregated analysis
SELECT gender_concept_id, COUNT(*) FROM person 
GROUP BY 1 HAVING COUNT(*) >= 5 LIMIT 100
```

### K-anonymity Enforcement
- Minimum group size: 5 records
- Small groups automatically suppressed
- Results validated before returning

### Rate Limiting
| Limit | Value |
|-------|-------|
| Per minute | 10 queries |
| Per hour | 100 queries |
| Max rows | 1000 per query |

### Audit Logging
- Logs query metadata (NOT results)
- Tracks tables accessed
- Records execution time
- Sanitizes error messages

---

## Privacy Best Practices

### ✅ DO

```sql
-- Aggregate data
SELECT gender_concept_id, COUNT(*) as n, AVG(value) as mean
FROM measurement
GROUP BY gender_concept_id
HAVING COUNT(*) >= 5
LIMIT 100

-- Use statistical functions
SELECT 
  measurement_concept_id,
  APPROX_QUANTILES(value_as_number, 4) as quartiles
FROM measurement
GROUP BY 1
LIMIT 50
```

### ❌ DON'T

```sql
-- Don't look up individual patients
SELECT * FROM person WHERE person_id = 12345

-- Don't export raw data
SELECT * FROM measurement LIMIT 10000

-- Don't find unique records
SELECT * FROM person GROUP BY 1 HAVING COUNT(*) = 1

-- Don't combine quasi-identifiers without aggregation
SELECT year_of_birth, gender_concept_id FROM person
```

---

## Troubleshooting

### BigQuery Connection Issues

```bash
# Re-authenticate
gcloud auth application-default login

# Verify project access
gcloud projects list

# Test connection
tulip validate
```

### Permission Denied

Contact datathon organizers to verify:
1. Your GCP account is granted access
2. The project ID is correct
3. The dataset name is correct

### Rate Limit Exceeded

Wait for the rate limit window to reset:
- Per minute: 60 seconds
- Per hour: Wait or reduce query frequency

### Query Blocked

If a query is blocked, it may be due to:
1. Re-identification risk detected
2. Missing LIMIT clause
3. SQL injection pattern detected

Use the suggested alternatives in the error message.

---

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
ruff check src/tulip/
ruff format src/tulip/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Ensure all security features remain intact
4. Submit a pull request

---

## License

### Tool License

MIT License - See [LICENSE](LICENSE) for details.

### Data License

AmsterdamUMCdb data is subject to its own [End User License Agreement](https://amsterdammedicaldatascience.nl/).
You must have approved access to use this tool with the database.

---

## Acknowledgments

- **AmsterdamUMCdb Team**: For making this valuable dataset available
- **ESICM**: For organizing the Van Gogh Datathon
- **Amsterdam Medical Data Science**: For data governance and access management
- **M3 Project**: Foundation code for MCP integration

---

## Contact

- **AmsterdamUMCdb Access**: access@amsterdammedicaldatascience.nl
- **Security Issues**: Report via GitHub Issues
- **Datathon Support**: Contact organizers via datathon channels

---

## Citation

If you use this tool in your research, please cite:

```bibtex
@software{tulip2026,
  title = {TULIP: Tool for UMCdb Language Interface and Processing},
  author = {[Your Team]},
  year = {2026},
  url = {https://github.com/[your-username]/TULIP}
}
```

And cite AmsterdamUMCdb:

```bibtex
@article{amsterdamumcdb2021,
  title = {AmsterdamUMCdb: Accessible and Structured Medical Data from the ICU},
  author = {Thoral, Patrick J and others},
  journal = {Critical Care Medicine},
  year = {2021}
}
```

---

<p align="center">
  🌷 TULIP - Secure ICU Data Analysis for the Van Gogh Datathon 🎨
</p>

