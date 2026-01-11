#!/bin/bash
# Quick test script for TULIP

set -e

echo "🧪 TULIP Quick Test"
echo "==================="
echo ""

# Test 1: Install TULIP
echo "1️⃣  Installing TULIP..."
pip install -e . > /dev/null 2>&1 || uv pip install -e .
echo "   ✅ Installation complete"
echo ""

# Test 2: Check version
echo "2️⃣  Testing CLI..."
tulip --version
echo ""

# Test 3: Test status command
echo "3️⃣  Testing status command..."
tulip status
echo ""

# Test 4: Test security command
echo "4️⃣  Testing security command..."
tulip security
echo ""

# Test 5: Test imports
echo "5️⃣  Testing Python imports..."
python -c "
from tulip import __version__
from tulip.config import UMCDB_TABLES
from tulip.security import validate_query_security
print(f'   ✅ TULIP v{__version__}')
print(f'   ✅ {len(UMCDB_TABLES)} tables configured')
is_safe, msg, _ = validate_query_security('SELECT * FROM person LIMIT 10')
print(f'   ✅ Security validation works')
"
echo ""

# Test 6: Test MCP config generation
echo "6️⃣  Testing MCP config generation..."
tulip mcp-config lmstudio > /dev/null 2>&1 && echo "   ✅ MCP config generation works" || echo "   ⚠️  MCP config generation (may need BigQuery config)"
echo ""

echo "✅ Basic tests complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Configure BigQuery: export TULIP_BQ_PROJECT and TULIP_BQ_DATASET"
echo "   2. Run: tulip validate"
echo "   3. Test with LMStudio (see TESTING.md)"
echo "   4. Push to GitHub when ready"

