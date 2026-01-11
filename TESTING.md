# 🧪 TULIP Testing Guide

Step-by-step guide to test TULIP before pushing to GitHub.

## Prerequisites Checklist

- [ ] Python 3.10+ installed
- [ ] Google Cloud SDK installed (`gcloud --version`)
- [ ] GCP authentication configured (`gcloud auth application-default login`)
- [ ] BigQuery project ID and dataset name from datathon organizers
- [ ] LMStudio installed (for final MCP testing)

---

## Step 1: Install TULIP Locally

```bash
cd /Users/rajnu/Desktop/MIT/1_Thesis_Research/Code/TULIP

# Install TULIP in editable mode
pip install -e .

# Or with uv
uv pip install -e .
```

**Verify installation:**
```bash
tulip --version
# Should show: 🌷 TULIP Version: 0.1.0
```

---

## Step 2: Test CLI Commands

### 2.1 Check Status (without BigQuery config)

```bash
tulip status
```

**Expected:** Should show status but warn about missing BigQuery configuration.

### 2.2 Configure BigQuery (if you have credentials)

```bash
# Set environment variables
export TULIP_BQ_PROJECT="your-project-id"
export TULIP_BQ_DATASET="amsterdamumcdb"

# Or use config command
tulip config --project-id your-project-id --dataset amsterdamumcdb
```

### 2.3 Validate Configuration

```bash
tulip validate
```

**Expected:** If configured correctly, shows ✅ Validation PASSED. If not configured, shows errors with helpful messages.

### 2.4 Test Security Command

```bash
tulip security
```

**Expected:** Shows security features and EULA compliance checklist.

### 2.5 Test MCP Config Generation

```bash
tulip mcp-config lmstudio
```

**Expected:** Prints JSON configuration for LMStudio.

---

## Step 3: Run Unit Tests (Optional but Recommended)

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock

# Run tests
pytest tests/

# Run with verbose output
pytest tests/ -v
```

**Expected:** All tests should pass (or skip if BigQuery not configured).

---

## Step 4: Test MCP Server Directly (Before LMStudio)

### 4.1 Test MCP Server Import

```bash
python -c "from tulip.mcp_server import main; print('✅ MCP server imports successfully')"
```

### 4.2 Test MCP Server Startup (STDIO mode)

**Note:** This will block waiting for input, so use Ctrl+C to exit.

```bash
python -m tulip.mcp_server
```

**Expected:** Server should start and wait for MCP protocol messages on stdin.

**Exit with:** `Ctrl+C`

---

## Step 5: Test with LMStudio (Full Integration)

### 5.1 Generate LMStudio Configuration

```bash
# Save config to a file
tulip mcp-config lmstudio > lmstudio_config.json

# Review the configuration
cat lmstudio_config.json
```

### 5.2 Configure LMStudio

1. Open LMStudio
2. Go to Settings → MCP Servers (or similar location)
3. Add a new MCP server
4. Paste the configuration from `lmstudio_config.json`
5. Ensure environment variables are set:
   ```bash
   export TULIP_BQ_PROJECT="your-project-id"
   export TULIP_BQ_DATASET="amsterdamumcdb"
   ```
6. Restart LMStudio

### 5.3 Test Queries in LMStudio

1. Load a model in LMStudio (e.g., gpt-oss-20b)
2. Open a chat window
3. Try asking:
   - "What tables are available in AmsterdamUMCdb?"
   - "Show me the database schema"
   - "What are the patient demographics?"
   - "Get measurement statistics"

**Expected:** The LLM should use TULIP's MCP tools to query the database.

---

## Step 6: Verify Security Features

### 6.1 Test Query Blocking

Try executing queries that should be blocked (you'll need to test this via the MCP server or add a test script):

```python
# Create test_security_queries.py
from tulip.security import validate_query_security

blocked_queries = [
    "SELECT * FROM person WHERE person_id = 12345 LIMIT 10",  # Direct lookup
    "SELECT * FROM person LIMIT 100",  # No LIMIT (should fail differently)
    "DROP TABLE person",  # Write operation
    "SELECT * FROM person; DROP TABLE person;",  # Multiple statements
]

for query in blocked_queries:
    is_safe, message, _ = validate_query_security(query)
    print(f"Query: {query[:50]}...")
    print(f"  Safe: {is_safe}, Message: {message[:60]}")
    print()
```

Run it:
```bash
python test_security_queries.py
```

**Expected:** All blocked queries should return `is_safe=False`.

---

## Step 7: Check for Common Issues

### Issue: Import Errors

```bash
python -c "import tulip; import tulip.config; import tulip.security; import tulip.mcp_server; print('✅ All imports work')"
```

### Issue: Missing Dependencies

```bash
pip install -e ".[dev]"  # Install all dependencies
```

### Issue: BigQuery Connection

```bash
# Verify GCP auth
gcloud auth application-default login

# Test BigQuery access
python -c "from google.cloud import bigquery; client = bigquery.Client(); print('✅ BigQuery client works')"
```

---

## Step 8: Before Pushing to GitHub

### 8.1 Check Git Status

```bash
git status
```

### 8.2 Review What Will Be Committed

```bash
git diff  # Check changes
```

### 8.3 Ensure Sensitive Data Not Committed

```bash
# Check for credentials in code
grep -r "your-project-id" src/ tests/  # Should find nothing
grep -r "amsterdamumcdb" src/ tests/ | grep -v "DATABASE_NAME\|dataset"  # Check for hardcoded values
```

### 8.4 Run Final Checks

```bash
# Syntax check
python -m py_compile src/tulip/*.py

# Import check
python -c "from tulip import __version__; print(f'✅ TULIP v{__version__} ready')"

# CLI check
tulip --version
```

---

## Step 9: Push to GitHub

Once all tests pass:

```bash
# Initialize git if not already done
git init

# Add files
git add .

# Commit
git commit -m "Initial TULIP implementation for Van Gogh Datathon"

# Create GitHub repo and push
# (Follow GitHub's instructions for new repo)
git remote add origin https://github.com/[your-username]/TULIP.git
git branch -M main
git push -u origin main
```

---

## Quick Test Checklist

Use this checklist before pushing:

- [ ] `tulip --version` works
- [ ] `tulip status` works
- [ ] `tulip security` shows compliance info
- [ ] `tulip mcp-config lmstudio` generates valid JSON
- [ ] Python imports work: `python -c "import tulip"`
- [ ] MCP server imports: `python -c "from tulip.mcp_server import main"`
- [ ] No hardcoded credentials in code
- [ ] `.gitignore` excludes sensitive files
- [ ] README.md exists and is accurate
- [ ] All tests pass (if BigQuery configured)

---

## Troubleshooting

### "Command not found: tulip"

```bash
# Ensure you're in a virtual environment with TULIP installed
pip install -e .
which tulip  # Should show path to tulip script
```

### "Module not found: tulip"

```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Ensure src/ is in path or install with -e flag
pip install -e .
```

### BigQuery Authentication Errors

```bash
# Re-authenticate
gcloud auth application-default login

# Verify project
gcloud config get-value project

# Set application default credentials
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

