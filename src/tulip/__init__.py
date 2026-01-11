"""
TULIP: Tool for UMCdb Language Interface and Processing

A secure MCP (Model Context Protocol) server for querying AmsterdamUMCdb
via local LLMs. Designed for the ESICM Datathon "Van Gogh" challenge.

IMPORTANT SECURITY NOTICE:
- This tool is designed for use with LOCAL models only (e.g., LMStudio with gpt-oss-20b)
- All data queries are performed via Google BigQuery - no local data storage
- This tool complies with the AmsterdamUMCdb End User License Agreement
- Do NOT attempt to re-identify patients or export raw data
- All code must be made available to AmsterdamUMCdb administrators

License: MIT (for the tool code)
Data License: AmsterdamUMCdb EULA (for data access)
"""

__version__ = "0.1.0"
__tool_name__ = "TULIP"
__full_name__ = "Tool for UMCdb Language Interface and Processing"
__datathon__ = "Van Gogh"
__database__ = "AmsterdamUMCdb"

