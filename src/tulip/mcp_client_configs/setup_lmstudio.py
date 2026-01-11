#!/usr/bin/env python3
"""
LMStudio MCP Configuration Setup for TULIP

This script generates the MCP server configuration for LMStudio
to use TULIP with local models like gpt-oss-20b.

Usage:
    python setup_lmstudio.py [--project-id PROJECT] [--dataset DATASET]
"""

import argparse
import json
import os
import sys
from pathlib import Path


def get_default_config_path() -> Path:
    """Get the default LMStudio config path based on OS."""
    if sys.platform == "darwin":
        # macOS
        return Path.home() / ".lmstudio" / "mcp_servers.json"
    elif sys.platform == "win32":
        # Windows
        return Path.home() / "AppData" / "Roaming" / "LMStudio" / "mcp_servers.json"
    else:
        # Linux
        return Path.home() / ".config" / "lmstudio" / "mcp_servers.json"


def generate_config(
    project_id: str | None = None,
    dataset: str | None = None,
) -> dict:
    """Generate TULIP MCP configuration for LMStudio."""
    
    # Build environment variables
    env_vars = {}
    
    if project_id:
        env_vars["TULIP_BQ_PROJECT"] = project_id
    elif os.getenv("TULIP_BQ_PROJECT"):
        env_vars["TULIP_BQ_PROJECT"] = os.getenv("TULIP_BQ_PROJECT")
    
    if dataset:
        env_vars["TULIP_BQ_DATASET"] = dataset
    elif os.getenv("TULIP_BQ_DATASET"):
        env_vars["TULIP_BQ_DATASET"] = os.getenv("TULIP_BQ_DATASET")
    
    # Python path
    python_path = sys.executable
    
    return {
        "tulip": {
            "command": python_path,
            "args": ["-m", "tulip.mcp_server"],
            "env": env_vars,
            "description": "TULIP - AmsterdamUMCdb MCP Server for Van Gogh Datathon",
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate TULIP MCP configuration for LMStudio"
    )
    parser.add_argument(
        "--project-id",
        help="Google Cloud project ID for BigQuery",
    )
    parser.add_argument(
        "--dataset",
        help="BigQuery dataset name containing AmsterdamUMCdb",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: print to stdout)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install to LMStudio config directory",
    )
    
    args = parser.parse_args()
    
    config = generate_config(
        project_id=args.project_id,
        dataset=args.dataset,
    )
    
    full_config = {"mcpServers": config}
    
    if args.install:
        config_path = get_default_config_path()
        
        # Load existing config if present
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
            existing.get("mcpServers", {}).update(config)
            full_config = existing
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(full_config, f, indent=2)
        
        print(f"✅ Configuration installed to: {config_path}")
        print()
        print("⚠️  Important next steps:")
        print("   1. Restart LMStudio to load the new configuration")
        print("   2. Ensure GCP authentication is configured:")
        print("      gcloud auth application-default login")
        print("   3. Select a local model (e.g., gpt-oss-20b) in LMStudio")
    
    elif args.output:
        with open(args.output, "w") as f:
            json.dump(full_config, f, indent=2)
        print(f"Configuration saved to: {args.output}")
    
    else:
        print(json.dumps(full_config, indent=2))


if __name__ == "__main__":
    main()

