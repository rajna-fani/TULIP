# TULIP: Tool for UMCdb Language Interface and Processing

A secure MCP (Model Context Protocol) server for querying AmsterdamUMCdb via local LLMs. Designed for the ESICM Datathon (Van Gogh snippet).

**⚠️ CRITICAL:** This tool complies with the AmsterdamUMCdb End User License Agreement. All code must be made available to AmsterdamUMCdb administrators. Use only with local LLMs (e.g., LMStudio). Never send queries or data to external LLM APIs.

## Features

- Query AmsterdamUMCdb (OMOP CDM) via BigQuery
- EULA-compliant security controls (k-anonymity, rate limiting, query validation)
- Works with local LLMs through LMStudio
- Dynamic schema discovery
- Aggregated query functions for safe data exploration

## Prerequisites

- Python 3.10+
- Google Cloud SDK (`gcloud`)
- BigQuery access credentials
- LMStudio (for local LLM usage)
- Project ID, dataset project ID, dataset name, and location from datathon organizers

## Installation

### Option 1: Install from GitHub

```bash
pip install git+https://github.com/[your-username]/TULIP.git
```

### Option 2: Clone and Install Locally

```bash
git clone https://github.com/[your-username]/TULIP.git
cd TULIP
pip install --break-system-packages -e .
```

**macOS users:** Add `--break-system-packages` flag if using Homebrew Python.

## Configuration

### 1. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

### 2. Configure TULIP

You need 4 values from the datathon organizers:
- **Project ID** (for authentication/billing, e.g., `cmi-lab`)
- **Dataset Project** (where data lives, e.g., `amsterdamumcdb`)
- **Dataset Name** (e.g., `van_gogh_2026_datathon`)
- **Location** (data region, e.g., `eu`)

Set them with:

```bash
tulip config \
  --project-id YOUR_PROJECT_ID \
  --dataset-project YOUR_DATASET_PROJECT \
  --dataset YOUR_DATASET_NAME \
  --location YOUR_LOCATION
```

Verify it works:

```bash
tulip validate
```

## LMStudio Setup

### 1. Get your Python path

```bash
which python3
```

Copy the output (e.g., `/opt/homebrew/bin/python3`).

### 2. Add TULIP to LMStudio

1. Open LMStudio → Settings → MCP Servers
2. Add this configuration (replace `YOUR_PYTHON_PATH` with the path from step 1):

```json
{
  "mcpServers": {
    "tulip": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["-m", "tulip.mcp_server"],
      "env": {
        "TULIP_BQ_PROJECT": "",
        "TULIP_BQ_DATASET_PROJECT": "",
        "TULIP_BQ_DATASET": "",
        "TULIP_BQ_LOCATION": ""
      }
    }
  }
}
```

3. Save and restart LMStudio
4. Load a model (e.g., gpt-oss-20b)
5. Test: "What tables are available?"

## Available MCP Tools

- `get_database_schema`: List all available tables with descriptions
- `get_table_info`: Get detailed schema information for a specific table
- `execute_umcdb_query`: Execute validated SQL queries (aggregated only)
- `get_patient_count`: Get total patient count
- `get_demographics_summary`: Summary statistics for patient demographics
- `get_visit_summary`: ICU admission statistics
- `get_condition_summary`: Diagnosis/condition statistics
- `get_medication_summary`: Medication administration statistics
- `get_procedure_summary`: Clinical procedure statistics
- `get_measurement_summary`: Clinical measurement statistics

## Security Features

- **SQL Injection Prevention**: Query parsing and validation
- **Re-identification Protection**: Blocks queries targeting individual patients
- **K-anonymity**: Minimum group size of 5 for aggregated results
- **Rate Limiting**: 100 queries/hour, 10 queries/minute
- **Query Audit Logging**: Metadata-only logging (no results or patient data)
- **Row Limits**: Maximum 1000 rows per query

## EULA Compliance

This tool adheres to the AmsterdamUMCdb End User License Agreement:

- ✅ Uses only local LLMs (no external API calls)
- ✅ Aggregated queries only (no individual patient records)
- ✅ K-anonymity enforcement (minimum group size: 5)
- ✅ Privacy-preserving audit logging (metadata only)
- ✅ Code available to AmsterdamUMCdb administrators
- ✅ Access restricted to datathon period

## Command-Line Interface

```bash
# Check status
tulip status

# View configuration
tulip config --show

# Validate setup
tulip validate

# Generate LMStudio config
tulip mcp-config lmstudio

# View security information
tulip security
```

## Project Structure

```
TULIP/
├── src/tulip/
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Configuration management
│   ├── security.py          # Security controls and validation
│   ├── mcp_server.py        # MCP server implementation
│   └── cli.py               # Command-line interface
├── pyproject.toml           # Project metadata and dependencies
└── README.md                # This file
```

## Troubleshooting

**Installation fails:** Add `--break-system-packages` flag (macOS with Homebrew Python)

**LMStudio can't find TULIP:** Use the correct Python path from `which python3` in LMStudio config

**Can't connect to BigQuery:** Run `gcloud auth application-default login` and `tulip validate`

## License

This project is provided for the ESICM Datathon. All code must be made available to AmsterdamUMCdb administrators as per EULA requirements.

## Citation

If you use TULIP in your research, please cite:

```
TULIP: Tool for UMCdb Language Interface and Processing
ESICM Datathon 2026 - Van Gogh Snippet
```

## Support

For datathon-specific questions, contact the datathon organizers. For technical issues, check the troubleshooting section above.
