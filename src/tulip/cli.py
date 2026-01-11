"""
TULIP CLI - Tool for UMCdb Language Interface and Processing

Command-line interface for configuring and managing TULIP for use with
local LLMs via LMStudio.

Commands:
- tulip config: Configure BigQuery credentials and LMStudio settings
- tulip status: Show current configuration and security status
- tulip validate: Validate configuration and test connection
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from tulip import __version__, __tool_name__, __full_name__, __datathon__
from tulip.config import (
    APP_NAME,
    DATABASE_NAME,
    FULL_NAME,
    UMCDB_TABLES,
    get_bigquery_config,
    get_datathon_period_status,
    is_within_datathon_period,
    load_runtime_config,
    logger,
    save_runtime_config,
    validate_bigquery_config,
)

app = typer.Typer(
    name="tulip",
    help=f"🌷 {FULL_NAME} - Secure MCP tool for {DATABASE_NAME} via local LLMs.",
    add_completion=False,
    rich_markup_mode="markdown",
)


def version_callback(value: bool):
    if value:
        typer.echo(f"🌷 TULIP Version: {__version__}")
        typer.echo(f"   {__full_name__}")
        typer.echo(f"   Datathon: {__datathon__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show CLI version.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-V",
            help="Enable DEBUG level logging.",
        ),
    ] = False,
):
    """
    🌷 TULIP CLI - Secure MCP tool for AmsterdamUMCdb.
    """
    tulip_logger = logging.getLogger(APP_NAME)
    if verbose:
        tulip_logger.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled.")


@app.command("status")
def status_cmd():
    """📊 Show current configuration and security status."""
    
    typer.secho(f"\n🌷 {FULL_NAME}", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.secho(f"   Version: {__version__}", fg=typer.colors.WHITE)
    typer.secho(f"   Datathon: {__datathon__}", fg=typer.colors.WHITE)
    
    # Datathon period status
    typer.echo()
    datathon_status = get_datathon_period_status()
    if is_within_datathon_period():
        typer.secho(datathon_status, fg=typer.colors.GREEN)
    else:
        typer.secho(datathon_status, fg=typer.colors.YELLOW)
    
    # BigQuery configuration
    typer.echo()
    typer.secho("☁️  BigQuery Configuration:", fg=typer.colors.BRIGHT_BLUE, bold=True)
    
    config = get_bigquery_config()
    is_valid, msg = validate_bigquery_config()
    
    if is_valid:
        typer.secho(f"   ✅ Project: {config['project']}", fg=typer.colors.GREEN)
        typer.secho(f"   ✅ Dataset: {config['dataset']}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"   ❌ {msg}", fg=typer.colors.RED)
        typer.echo()
        typer.secho("   To configure, set environment variables:", fg=typer.colors.YELLOW)
        typer.echo("   export TULIP_BQ_PROJECT='your-project-id'")
        typer.echo("   export TULIP_BQ_DATASET='your-dataset-name'")
    
    # Runtime config
    typer.echo()
    typer.secho("⚙️  Runtime Configuration:", fg=typer.colors.BRIGHT_BLUE, bold=True)
    
    runtime_config = load_runtime_config()
    typer.echo(f"   Query limit default: {runtime_config.get('query_limit_default', 100)}")
    typer.echo(f"   Query limit max: {runtime_config.get('query_limit_max', 1000)}")
    typer.echo(f"   LMStudio host: {runtime_config.get('lmstudio_host', 'http://localhost:1234')}")
    typer.echo(f"   Model: {runtime_config.get('model_name', 'gpt-oss-20b')}")
    
    # Available tables
    typer.echo()
    typer.secho(f"📋 Available Tables ({DATABASE_NAME}):", fg=typer.colors.BRIGHT_BLUE, bold=True)
    for table_name, info in UMCDB_TABLES.items():
        typer.echo(f"   • {table_name}: {info['description']}")
    
    # Security status
    typer.echo()
    typer.secho("🔒 Security Features:", fg=typer.colors.BRIGHT_BLUE, bold=True)
    typer.echo("   ✅ SQL injection protection")
    typer.echo("   ✅ Re-identification prevention")
    typer.echo("   ✅ Rate limiting (100/hour, 10/minute)")
    typer.echo("   ✅ K-anonymity enforcement (min group size: 5)")
    typer.echo("   ✅ Query audit logging")
    typer.echo()


@app.command("config")
def config_cmd(
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id",
            "-p",
            help="Google Cloud project ID for BigQuery.",
        ),
    ] = None,
    dataset: Annotated[
        str | None,
        typer.Option(
            "--dataset",
            "-d",
            help="BigQuery dataset name containing AmsterdamUMCdb.",
        ),
    ] = None,
    lmstudio_host: Annotated[
        str | None,
        typer.Option(
            "--lmstudio-host",
            help="LMStudio API host (default: http://localhost:1234).",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Model name for LMStudio (default: gpt-oss-20b).",
        ),
    ] = None,
    show: Annotated[
        bool,
        typer.Option(
            "--show",
            help="Show current configuration without modifying.",
        ),
    ] = False,
):
    """⚙️  Configure TULIP settings for BigQuery and LMStudio.
    
    **Examples:**
    
    • Set BigQuery configuration:
      `tulip config --project-id my-project --dataset amsterdamumcdb`
    
    • Set LMStudio configuration:
      `tulip config --lmstudio-host http://localhost:1234 --model gpt-oss-20b`
    
    • Show current config:
      `tulip config --show`
    """
    if show:
        config = load_runtime_config()
        typer.echo(json.dumps(config, indent=2))
        return
    
    # Load existing config
    config = load_runtime_config()
    modified = False
    
    if project_id:
        config["bigquery_project"] = project_id
        modified = True
        typer.secho(f"✅ BigQuery project set to: {project_id}", fg=typer.colors.GREEN)
    
    if dataset:
        config["bigquery_dataset"] = dataset
        modified = True
        typer.secho(f"✅ BigQuery dataset set to: {dataset}", fg=typer.colors.GREEN)
    
    if lmstudio_host:
        config["lmstudio_host"] = lmstudio_host
        modified = True
        typer.secho(f"✅ LMStudio host set to: {lmstudio_host}", fg=typer.colors.GREEN)
    
    if model:
        config["model_name"] = model
        modified = True
        typer.secho(f"✅ Model set to: {model}", fg=typer.colors.GREEN)
    
    if modified:
        save_runtime_config(config)
        typer.echo()
        typer.secho("💾 Configuration saved!", fg=typer.colors.BRIGHT_GREEN)
        typer.echo()
        typer.secho("⚠️  Note: Environment variables take precedence over config file.", fg=typer.colors.YELLOW)
        typer.echo("   To use config file values, ensure TULIP_BQ_PROJECT and")
        typer.echo("   TULIP_BQ_DATASET are not set in your environment.")
    else:
        typer.echo("No configuration changes specified.")
        typer.echo()
        typer.echo("Usage examples:")
        typer.echo("  tulip config --project-id my-gcp-project --dataset amsterdamumcdb")
        typer.echo("  tulip config --show")


@app.command("validate")
def validate_cmd():
    """✅ Validate configuration and test BigQuery connection.
    
    This command:
    1. Checks BigQuery configuration
    2. Tests BigQuery connection
    3. Verifies access to AmsterdamUMCdb tables
    """
    typer.secho("\n🔍 Validating TULIP Configuration...\n", fg=typer.colors.BRIGHT_BLUE, bold=True)
    
    errors = []
    warnings = []
    
    # Check 1: BigQuery configuration
    typer.echo("1️⃣  Checking BigQuery configuration...")
    is_valid, msg = validate_bigquery_config()
    if is_valid:
        typer.secho(f"   ✅ {msg}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"   ❌ {msg}", fg=typer.colors.RED)
        errors.append(msg)
    
    # Check 2: Datathon period
    typer.echo("\n2️⃣  Checking datathon period...")
    if is_within_datathon_period():
        typer.secho("   ✅ Within datathon period", fg=typer.colors.GREEN)
    else:
        status = get_datathon_period_status()
        typer.secho(f"   ⚠️  {status}", fg=typer.colors.YELLOW)
        warnings.append("Outside datathon period - access may be restricted")
    
    # Check 3: BigQuery connection (only if config is valid)
    if is_valid:
        typer.echo("\n3️⃣  Testing BigQuery connection...")
        try:
            from google.cloud import bigquery
            
            config = get_bigquery_config()
            client = bigquery.Client(project=config["project"])
            
            # Try a simple query
            test_query = f"""
            SELECT table_name 
            FROM `{config['project']}.{config['dataset']}.INFORMATION_SCHEMA.TABLES`
            LIMIT 1
            """
            
            result = client.query(test_query).result()
            typer.secho("   ✅ BigQuery connection successful", fg=typer.colors.GREEN)
            
            # List available tables
            typer.echo("\n4️⃣  Checking available tables...")
            tables_query = f"""
            SELECT table_name 
            FROM `{config['project']}.{config['dataset']}.INFORMATION_SCHEMA.TABLES`
            ORDER BY table_name
            """
            tables = [row.table_name for row in client.query(tables_query).result()]
            
            if tables:
                typer.secho(f"   ✅ Found {len(tables)} tables:", fg=typer.colors.GREEN)
                for table in tables[:10]:
                    typer.echo(f"      • {table}")
                if len(tables) > 10:
                    typer.echo(f"      ... and {len(tables) - 10} more")
            else:
                typer.secho("   ⚠️  No tables found in dataset", fg=typer.colors.YELLOW)
                warnings.append("No tables found - check dataset name")
        
        except ImportError:
            typer.secho("   ❌ google-cloud-bigquery not installed", fg=typer.colors.RED)
            errors.append("Install with: pip install google-cloud-bigquery")
        
        except Exception as e:
            typer.secho(f"   ❌ Connection failed: {e}", fg=typer.colors.RED)
            errors.append(f"BigQuery connection error: {e}")
    
    # Summary
    typer.echo("\n" + "="*50)
    if errors:
        typer.secho("❌ Validation FAILED", fg=typer.colors.RED, bold=True)
        typer.echo("\nErrors:")
        for error in errors:
            typer.secho(f"  • {error}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    elif warnings:
        typer.secho("⚠️  Validation PASSED with warnings", fg=typer.colors.YELLOW, bold=True)
        typer.echo("\nWarnings:")
        for warning in warnings:
            typer.secho(f"  • {warning}", fg=typer.colors.YELLOW)
    else:
        typer.secho("✅ Validation PASSED", fg=typer.colors.GREEN, bold=True)
    
    typer.echo()


@app.command("mcp-config")
def mcp_config_cmd(
    client: Annotated[
        str | None,
        typer.Argument(
            help="MCP client to configure (e.g., 'lmstudio', 'claude').",
        ),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Save configuration to file.",
        ),
    ] = None,
):
    """🔧 Generate MCP configuration for LLM clients.
    
    **For LMStudio users:**
    
    This generates the MCP server configuration needed to use TULIP
    with LMStudio and local models like gpt-oss-20b.
    
    **Example:**
    
    `tulip mcp-config lmstudio`
    """
    # Get current Python path and configuration
    python_path = sys.executable
    config = get_bigquery_config()
    runtime_config = load_runtime_config()
    
    # Build environment variables
    env_vars = {}
    
    if config.get("project"):
        env_vars["TULIP_BQ_PROJECT"] = config["project"]
    if config.get("dataset"):
        env_vars["TULIP_BQ_DATASET"] = config["dataset"]
    
    # Generate MCP configuration
    mcp_config = {
        "mcpServers": {
            "tulip": {
                "command": python_path,
                "args": ["-m", "tulip.mcp_server"],
                "env": env_vars,
            }
        }
    }
    
    # Alternative using uvx (if available)
    uvx_config = {
        "mcpServers": {
            "tulip": {
                "command": "uvx",
                "args": ["tulip-mcp"],
                "env": env_vars,
            }
        }
    }
    
    typer.secho("\n🔧 TULIP MCP Configuration\n", fg=typer.colors.BRIGHT_BLUE, bold=True)
    
    if client and client.lower() == "lmstudio":
        typer.secho("📋 LMStudio Configuration:", fg=typer.colors.BRIGHT_GREEN, bold=True)
        typer.echo()
        typer.echo("1. Open LMStudio Settings > MCP Servers")
        typer.echo("2. Add a new server with this configuration:")
        typer.echo()
    
    typer.secho("Option 1 - Using Python directly:", fg=typer.colors.WHITE, bold=True)
    typer.echo(json.dumps(mcp_config, indent=2))
    
    typer.echo()
    typer.secho("Option 2 - Using uvx (recommended if installed):", fg=typer.colors.WHITE, bold=True)
    typer.echo(json.dumps(uvx_config, indent=2))
    
    if output:
        with open(output, "w") as f:
            json.dump(mcp_config, f, indent=2)
        typer.secho(f"\n💾 Configuration saved to: {output}", fg=typer.colors.GREEN)
    
    typer.echo()
    typer.secho("⚠️  Important:", fg=typer.colors.YELLOW, bold=True)
    typer.echo("   • Ensure TULIP_BQ_PROJECT and TULIP_BQ_DATASET are configured")
    typer.echo("   • Set up GCP authentication (gcloud auth application-default login)")
    typer.echo("   • Use local models only - do not send data to external APIs")
    typer.echo()


@app.command("security")
def security_cmd():
    """🔒 Show detailed security information and EULA compliance.
    
    Displays:
    - Current security policies
    - Rate limiting status
    - EULA compliance checklist
    """
    typer.secho("\n🔒 TULIP Security & Compliance Information\n", fg=typer.colors.BRIGHT_BLUE, bold=True)
    
    # EULA Compliance
    typer.secho("📜 EULA Compliance Checklist:", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo()
    
    eula_items = [
        ("✅", "BigQuery-only access (no local data storage)"),
        ("✅", "Time-limited to datathon period (Jan-Feb 2026)"),
        ("✅", "No downloading, copying, or moving data"),
        ("✅", "No sharing access with unauthorized users"),
        ("✅", "Non-commercial, scientific research only"),
        ("✅", "No re-identification attempts blocked"),
        ("✅", "All code available on GitHub"),
        ("✅", "Query audit trail maintained"),
    ]
    
    for icon, item in eula_items:
        typer.echo(f"   {icon} {item}")
    
    # Security Features
    typer.echo()
    typer.secho("🛡️  Active Security Features:", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo()
    
    features = [
        ("SQL Injection Protection", "Validates all queries, blocks injection patterns"),
        ("Re-identification Prevention", "Blocks queries that could identify individuals"),
        ("Rate Limiting", "100 queries/hour, 10 queries/minute"),
        ("K-anonymity Enforcement", "Minimum group size of 5 in aggregations"),
        ("Query Limits", "Maximum 1000 rows per query"),
        ("Audit Logging", "Logs query metadata (not results) for compliance"),
        ("Result Privacy Checks", "Validates results before returning"),
    ]
    
    for feature, description in features:
        typer.echo(f"   • {feature}")
        typer.echo(f"     {description}")
        typer.echo()
    
    # Privacy Recommendations
    typer.secho("💡 Privacy Best Practices:", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo()
    typer.echo("   1. Use aggregated queries (COUNT, AVG, etc.) for analysis")
    typer.echo("   2. Avoid querying individual patient records")
    typer.echo("   3. Use GROUP BY with HAVING COUNT(*) >= 5")
    typer.echo("   4. Report any suspected re-identification to administrators")
    typer.echo("   5. Keep your GCP credentials secure")
    typer.echo()
    
    # Contact
    typer.secho("📧 Contact:", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo()
    typer.echo("   AmsterdamUMCdb administrators: access@amsterdammedicaldatascience.nl")
    typer.echo("   Report security issues: [datathon organizers]")
    typer.echo()


if __name__ == "__main__":
    app()

