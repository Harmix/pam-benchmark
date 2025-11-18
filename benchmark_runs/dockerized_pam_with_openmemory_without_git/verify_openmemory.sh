#!/bin/bash

# OpenMemory Installation Verification Script

echo "========================================"
echo "OpenMemory Installation Verification"
echo "========================================"
echo ""

# Color output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

ERRORS=0

# 1. Check OpenMemory directory
echo "1. Checking OpenMemory installation..."
if [ -d "/openmemory/mem0/openmemory" ]; then
    check_pass "OpenMemory directory exists"

    if [ -d "/openmemory/mem0/openmemory/api" ]; then
        check_pass "API directory found"
    else
        check_fail "API directory not found"
        ERRORS=$((ERRORS + 1))
    fi

    if [ -d "/openmemory/mem0/openmemory/ui" ]; then
        check_pass "UI directory found"
    else
        check_fail "UI directory not found"
        ERRORS=$((ERRORS + 1))
    fi
else
    check_fail "OpenMemory directory not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 2. Check Python dependencies
echo "2. Checking Python dependencies..."
REQUIRED_PACKAGES=("fastapi" "uvicorn" "pydantic" "mem0ai")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        check_pass "$package installed"
    else
        check_fail "$package not installed"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# 3. Check Node.js and pnpm
echo "3. Checking Node.js environment..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    check_pass "Node.js installed: $NODE_VERSION"
else
    check_fail "Node.js not installed"
    ERRORS=$((ERRORS + 1))
fi

if command -v pnpm &> /dev/null; then
    PNPM_VERSION=$(pnpm --version)
    check_pass "pnpm installed: $PNPM_VERSION"
else
    check_fail "pnpm not installed"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 4. Check environment variables
echo "4. Checking environment variables..."
if [ -n "$ANTHROPIC_API_KEY" ]; then
    check_pass "ANTHROPIC_API_KEY set"
else
    check_fail "ANTHROPIC_API_KEY not set"
    ERRORS=$((ERRORS + 1))
fi

if [ -n "$OPENAI_API_KEY" ]; then
    check_pass "OPENAI_API_KEY set"
else
    check_fail "OPENAI_API_KEY not set"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 5. Check memory directories
echo "5. Checking memory storage..."
if [ -d "/openmemory/memories" ]; then
    check_pass "Memory base directory exists"
    MEMORY_COUNT=$(find /openmemory/memories -type d -maxdepth 2 | wc -l)
    check_pass "Memory subdirectories: $((MEMORY_COUNT - 1))"
else
    check_warn "Memory directory doesn't exist yet (will be created on first run)"
fi
echo ""

# 6. Test OpenMemory startup
echo "6. Testing OpenMemory startup..."
TEST_USER="verify_test_$(date +%s)"

if /usr/local/bin/openmemory_setup.sh start "$TEST_USER" "test_config" > /tmp/openmemory_test.log 2>&1; then
    check_pass "OpenMemory started successfully"

    sleep 5

    # Check if API is responding
    if curl -s http://localhost:8765/health > /dev/null 2>&1; then
        check_pass "API is responding"
    else
        check_fail "API is not responding"
        ERRORS=$((ERRORS + 1))
    fi

    # Check if UI port is open
    if nc -z localhost 3000 2>/dev/null; then
        check_pass "UI port is open"
    else
        check_warn "UI port not responding (may still be starting)"
    fi

    # Test memory creation
    MEMORY_TEST=$(curl -s -X POST http://localhost:8765/memories \
        -H "Content-Type: application/json" \
        -d "{\"user_id\": \"$TEST_USER\", \"messages\": [{\"role\": \"user\", \"content\": \"Test memory\"}]}")

    if [ $? -eq 0 ]; then
        check_pass "Memory creation test passed"
    else
        check_fail "Memory creation test failed"
        ERRORS=$((ERRORS + 1))
    fi

    # Test memory retrieval
    MEMORY_RETRIEVE=$(curl -s "http://localhost:8765/memories?user_id=$TEST_USER")
    if [ $? -eq 0 ] && [ -n "$MEMORY_RETRIEVE" ]; then
        check_pass "Memory retrieval test passed"
    else
        check_fail "Memory retrieval test failed"
        ERRORS=$((ERRORS + 1))
    fi

    # Cleanup
    /usr/local/bin/openmemory_setup.sh stop > /dev/null 2>&1
    check_pass "Test cleanup completed"
else
    check_fail "OpenMemory failed to start"
    cat /tmp/openmemory_test.log
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 7. Check MCP integration
echo "7. Checking MCP integration..."
if command -v claude &> /dev/null; then
    check_pass "Claude CLI installed"
else
    check_fail "Claude CLI not installed"
    ERRORS=$((ERRORS + 1))
fi

if [ -x /usr/local/bin/openmemory_setup.sh ]; then
    check_pass "OpenMemory setup script is executable"
else
    check_fail "OpenMemory setup script not executable"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Summary
echo "========================================"
echo "Verification Summary"
echo "========================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "OpenMemory is ready to use. Next steps:"
    echo "1. Start OpenMemory: /usr/local/bin/openmemory_setup.sh start <user_id>"
    echo "2. Access UI: http://localhost:3000"
    echo "3. Access API: http://localhost:8765"
    echo "4. View docs: http://localhost:8765/docs"
    echo ""
    exit 0
else
    echo -e "${RED}Found $ERRORS error(s)${NC}"
    echo ""
    echo "Please check the errors above and:"
    echo "1. Ensure all environment variables are set in .env file"
    echo "2. Rebuild the Docker container if needed: docker-compose up -d --build"
    echo "3. Check logs at /tmp/openmemory_*.log"
    echo ""
    exit 1
fi