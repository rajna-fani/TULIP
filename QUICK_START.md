# 🚀 TULIP Quick Start

## Testing Before Pushing to GitHub

**Recommended workflow:** Test locally first, then push to GitHub.

---

## Step 1: Install TULIP Locally (2 minutes)

```bash
cd /Users/rajnu/Desktop/MIT/1_Thesis_Research/Code/TULIP

# Install in editable mode
pip install -e .

# Or with uv
uv pip install -e .
```

**Verify:**
```bash
tulip --version
# Should show: 🌷 TULIP Version: 0.1.0
```

---

## Step 2: Quick Test (1 minute)

Run the quick test script:

```bash
./quick_test.sh
```

Or test manually:

```bash
# Test CLI
tulip --version
tulip status
tulip security

# Test Python imports
python -c "from tulip import __version__; print(f'TULIP v{__version__}')"
```

---

## Step 3: Configure BigQuery (If You Have Credentials)

```bash
# Set environment variables (from datathon organizers)
export TULIP_BQ_PROJECT="your-project-id"
export TULIP_BQ_DATASET="amsterdamumcdb"

# Authenticate with Google Cloud
gcloud auth application-default login

# Validate
tulip validate
```

**If you don't have credentials yet:** That's OK! You can still:
- ✅ Test CLI commands
- ✅ Test MCP config generation
- ✅ Test security features
- ✅ Push to GitHub

---

## Step 4: Test with LMStudio (Optional, 5 minutes)

### 4.1 Generate Configuration

```bash
tulip mcp-config lmstudio
```

Copy the JSON output.

### 4.2 Configure LMStudio

1. Open LMStudio
2. Settings → MCP Servers
3. Add new server with the JSON config
4. Set environment variables:
   ```bash
   export TULIP_BQ_PROJECT="your-project-id"
   export TULIP_BQ_DATASET="amsterdamumcdb"
   ```
5. Restart LMStudio
6. Load a model (e.g., gpt-oss-20b)
7. Try: "What tables are in AmsterdamUMCdb?"

---

## Step 5: Push to GitHub (When Ready)

```bash
# Review what will be committed
git status
git diff

# Ensure no sensitive data
grep -r "your-project-id" src/ tests/  # Should be empty

# Commit and push
git add .
git commit -m "Initial TULIP implementation for Van Gogh Datathon"
git remote add origin https://github.com/[your-username]/TULIP.git
git push -u origin main
```

---

## ✅ Pre-Push Checklist

- [ ] `tulip --version` works
- [ ] `tulip status` shows info
- [ ] `tulip security` shows compliance
- [ ] No hardcoded credentials in code
- [ ] `.gitignore` is in place
- [ ] README.md looks good
- [ ] Tests pass (optional: `pytest tests/`)

---

## 🎯 What to Test Right Now

**You can test these immediately (no BigQuery needed):**

1. ✅ CLI commands work
2. ✅ Python imports work
3. ✅ Security validation works
4. ✅ MCP config generation works
5. ✅ Code structure is correct

**You need BigQuery credentials for:**
- ❌ `tulip validate` (tests connection)
- ❌ LMStudio integration
- ❌ Actual database queries

---

## 💡 Recommendation

**Do this now:**
1. Run `./quick_test.sh` or test manually
2. Verify CLI works
3. Review code structure
4. **Push to GitHub** ✅

**Do this later (when you have credentials):**
1. Configure BigQuery
2. Test with LMStudio
3. Test actual queries

---

## Need Help?

See `TESTING.md` for detailed testing guide.

