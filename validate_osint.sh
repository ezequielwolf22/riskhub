#!/bin/bash
# validate_osint.sh - Validate OSINT integration in RiskHub

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        RiskHub OSINT Integration Validation Script             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

passed=0
failed=0

# Helper functions
check_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((passed++))
}

check_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((failed++))
}

check_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

echo "1. Checking backend files..."
echo "─────────────────────────────────────────────────────────────────"

for file in \
    "app/services/osint_hibp.py" \
    "app/services/osint_virustotal.py" \
    "app/services/osint_leakcheck.py" \
    "app/services/osint_intelx.py" \
    "app/services/osint_github.py" \
    "app/services/osint_engine.py" \
    "app/routers/osint.py"
do
    if [ -f "$file" ]; then
        check_pass "File exists: $file"
    else
        check_fail "File missing: $file"
    fi
done

echo ""
echo "2. Checking frontend files..."
echo "─────────────────────────────────────────────────────────────────"

if [ -f "app/static/js/views/osint.js" ]; then
    check_pass "Frontend view exists: app/static/js/views/osint.js"
else
    check_fail "Frontend view missing: app/static/js/views/osint.js"
fi

echo ""
echo "3. Checking model definitions..."
echo "─────────────────────────────────────────────────────────────────"

if grep -q "class OSINTScan" app/models.py; then
    check_pass "OSINTScan model defined"
else
    check_fail "OSINTScan model not found"
fi

if grep -q "class OSINTFinding" app/models.py; then
    check_pass "OSINTFinding model defined"
else
    check_fail "OSINTFinding model not found"
fi

if grep -q "class OSINTIdentifier" app/models.py; then
    check_pass "OSINTIdentifier model defined"
else
    check_fail "OSINTIdentifier model not found"
fi

echo ""
echo "4. Checking schema definitions..."
echo "─────────────────────────────────────────────────────────────────"

if grep -q "class OSINTScanResponse" app/schemas.py; then
    check_pass "OSINT schemas defined"
else
    check_fail "OSINT schemas not found"
fi

echo ""
echo "5. Checking router registration..."
echo "─────────────────────────────────────────────────────────────────"

if grep -q "from app.routers import.*osint" app/main.py; then
    check_pass "OSINT router imported in main.py"
else
    check_fail "OSINT router not imported"
fi

if grep -q "app.include_router(osint.router)" app/main.py; then
    check_pass "OSINT router registered"
else
    check_fail "OSINT router not registered"
fi

echo ""
echo "6. Checking configuration..."
echo "─────────────────────────────────────────────────────────────────"

if grep -q "hibp_api_key" app/config.py; then
    check_pass "HIBP API key config defined"
else
    check_fail "HIBP API key config not found"
fi

if grep -q "RISKHUB_HIBP_API_KEY" .env.example; then
    check_pass ".env.example includes OSINT variables"
else
    check_warn ".env.example missing OSINT variables"
fi

echo ""
echo "7. Checking frontend integration..."
echo "─────────────────────────────────────────────────────────────────"

if grep -q "osint: ViewOsint" app/static/js/app.js; then
    check_pass "OSINT route registered in app.js"
else
    check_fail "OSINT route not in app.js"
fi

if grep -q "osint.js" app/static/index.html; then
    check_pass "OSINT script loaded in HTML"
else
    check_fail "OSINT script not in HTML"
fi

if grep -q "data-route=\"osint\"" app/static/index.html; then
    check_pass "OSINT menu item in sidebar"
else
    check_fail "OSINT menu item not in sidebar"
fi

echo ""
echo "8. Checking documentation..."
echo "─────────────────────────────────────────────────────────────────"

if [ -f "OSINT_INTEGRATION.md" ]; then
    check_pass "Documentation file exists: OSINT_INTEGRATION.md"
else
    check_warn "Documentation missing: OSINT_INTEGRATION.md"
fi

if [ -f "OSINT_SUMMARY.txt" ]; then
    check_pass "Summary file exists: OSINT_SUMMARY.txt"
else
    check_warn "Summary missing: OSINT_SUMMARY.txt"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "VALIDATION RESULTS"
echo "════════════════════════════════════════════════════════════════"
echo -e "Passed: ${GREEN}$passed${NC}"
echo -e "Failed: ${RED}$failed${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ OSINT integration validation PASSED${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Configure API keys in .env (optional)"
    echo "  2. Start the app: uvicorn app.main:app --reload"
    echo "  3. Access at: http://localhost:8000/#/osint"
    exit 0
else
    echo -e "${RED}❌ OSINT integration validation FAILED${NC}"
    echo "Please check the missing files above."
    exit 1
fi
