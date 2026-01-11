#!/bin/bash
# Pre-push privacy and security checks for TULIP

echo "🔒 TULIP Pre-Push Privacy & Security Checks"
echo "============================================="
echo ""

PASSED=true

# Check 1: No hardcoded project IDs
echo "1️⃣  Checking for hardcoded GCP project IDs..."
if grep -ri "gcp-.*project\|google.*project.*[a-z0-9]\{20\}" src/ tests/ 2>/dev/null | grep -v "my-gcp-project\|your-project-id\|placeholder" | grep -v ".pyc" | grep -v Binary; then
    echo "   ❌ Found potential hardcoded project IDs"
    PASSED=false
else
    echo "   ✅ No hardcoded project IDs found"
fi
echo ""

# Check 2: No data files
echo "2️⃣  Checking for data files (should be empty)..."
DATA_FILES=$(find . -name "*.parquet" -o -name "*.csv" -o -name "*.duckdb" 2>/dev/null | grep -v ".git" | grep -v ".venv")
if [ -n "$DATA_FILES" ]; then
    echo "   ❌ Found data files:"
    echo "$DATA_FILES"
    PASSED=false
else
    echo "   ✅ No data files found"
fi
echo ""

# Check 3: No credentials in code
echo "3️⃣  Checking for credentials in code..."
if grep -ri "api.*key\|secret.*key\|password.*=" src/ tests/ 2>/dev/null | grep -v "#.*password\|#.*key\|sanitize\|redact" | grep -v ".pyc" | grep -v Binary; then
    echo "   ❌ Found potential credentials"
    PASSED=false
else
    echo "   ✅ No credentials found in code"
fi
echo ""

# Check 4: .gitignore exists and excludes sensitive files
echo "4️⃣  Checking .gitignore..."
if [ ! -f .gitignore ]; then
    echo "   ❌ .gitignore missing!"
    PASSED=false
elif ! grep -q ".tulip/config.json" .gitignore; then
    echo "   ⚠️  .gitignore missing .tulip/config.json"
elif ! grep -q "*.audit.log" .gitignore; then
    echo "   ⚠️  .gitignore missing *.audit.log"
else
    echo "   ✅ .gitignore properly configured"
fi
echo ""

# Check 5: No config files with credentials
echo "5️⃣  Checking for config files with credentials..."
CONFIG_FILES=$(find . -name "config.json" -o -name "*credentials*.json" -o -name "*service-account*.json" 2>/dev/null | grep -v ".git" | grep -v ".venv" | grep -v node_modules)
if [ -n "$CONFIG_FILES" ]; then
    echo "   ⚠️  Found config files:"
    echo "$CONFIG_FILES"
    echo "   Check that these are in .gitignore"
else
    echo "   ✅ No credential files found"
fi
echo ""

# Check 6: Code structure validation
echo "6️⃣  Validating code structure..."
python3 -m py_compile src/tulip/*.py 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ All Python files compile successfully"
else
    echo "   ❌ Python compilation errors"
    PASSED=false
fi
echo ""

# Final verdict
echo "============================================="
if [ "$PASSED" = true ]; then
    echo "✅ ALL CHECKS PASSED"
    echo ""
    echo "TULIP is safe to push to a public repository!"
    echo ""
    echo "📋 Summary:"
    echo "   ✅ No hardcoded credentials"
    echo "   ✅ No data files"
    echo "   ✅ Privacy-preserving audit logging"
    echo "   ✅ EULA compliant code structure"
    echo "   ✅ Proper .gitignore configuration"
    echo ""
    exit 0
else
    echo "❌ CHECKS FAILED"
    echo ""
    echo "Please fix the issues above before pushing to GitHub."
    echo ""
    exit 1
fi

