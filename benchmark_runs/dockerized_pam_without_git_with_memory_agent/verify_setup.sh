#!/bin/bash

# Verification script for benchmark environment
echo "========================================"
echo "Benchmark Environment Verification"
echo "========================================"
echo ""

# Check for required files
echo "Checking required files..."
MISSING_FILES=0

# Core files
FILES_TO_CHECK=(
    "docker-compose.yml"
    "Dockerfile"
    ".env"
    "setup_and_run.sh"
    "run_all_isolated.sh"
    "run_range_isolated.sh"
    "INIT.md"
    "init.py"
    "INTRO_TEMPLATE.md"
    "CLAUDE.md"
)

for FILE in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$FILE" ]; then
        echo "✓ $FILE"
    else
        echo "✗ $FILE (MISSING)"
        ((MISSING_FILES++))
    fi
done

echo ""

# Check directories
echo "Checking required directories..."
DIRS_TO_CHECK=(
    "test_configs"
    "test_event_histories"
    "outputs"
    "claude-config"
)

for DIR in "${DIRS_TO_CHECK[@]}"; do
    if [ -d "$DIR" ]; then
        COUNT=$(ls -1 "$DIR" 2>/dev/null | wc -l)
        echo "✓ $DIR/ (contains $COUNT items)"
    else
        echo "✗ $DIR/ (MISSING)"
        ((MISSING_FILES++))
    fi
done

echo ""

# Check .env file
if [ -f ".env" ]; then
    echo "Checking .env file..."
    if grep -q "ANTHROPIC_API_KEY=" ".env"; then
        echo "✓ ANTHROPIC_API_KEY is set"
    else
        echo "✗ ANTHROPIC_API_KEY not found in .env"
        echo "  Add: ANTHROPIC_API_KEY=your-key-here"
        ((MISSING_FILES++))
    fi
else
    echo "✗ .env file missing!"
    echo "  Create .env with: ANTHROPIC_API_KEY=your-key-here"
    ((MISSING_FILES++))
fi

echo ""

# Check Docker
echo "Checking Docker..."
if command -v docker &> /dev/null; then
    echo "✓ Docker is installed"
    if docker info &> /dev/null; then
        echo "✓ Docker daemon is running"
    else
        echo "✗ Docker daemon is not running"
        echo "  Start Docker first"
        ((MISSING_FILES++))
    fi
else
    echo "✗ Docker is not installed"
    ((MISSING_FILES++))
fi

if command -v docker-compose &> /dev/null; then
    echo "✓ Docker Compose is installed"
else
    echo "✗ Docker Compose is not installed"
    ((MISSING_FILES++))
fi

echo ""

# Check example configs
echo "Checking example configs..."
if [ -d "test_configs" ] && [ -f "test_configs/config_1.yaml" ]; then
    echo "✓ Found config_1.yaml"

    # Check if it has required fields
    if command -v yq &> /dev/null; then
        if yq eval '.linear' "test_configs/config_1.yaml" &> /dev/null; then
            echo "✓ config_1.yaml has 'linear' section"
        fi
        if yq eval '.benchmark.questions' "test_configs/config_1.yaml" &> /dev/null; then
            echo "✓ config_1.yaml has questions"
        fi
        if yq eval '.benchmark.event_history' "test_configs/config_1.yaml" &> /dev/null; then
            echo "✓ config_1.yaml has event_history reference"
        fi
    fi
fi

if [ -d "test_event_histories" ] && [ -f "test_event_histories/event_history_1.json" ]; then
    echo "✓ Found event_history_1.json"
    if command -v jq &> /dev/null; then
        EVENT_COUNT=$(jq '. | length' "test_event_histories/event_history_1.json" 2>/dev/null || echo 0)
        echo "  Contains $EVENT_COUNT events"
    fi
fi

echo ""

# Check PAM-specific files
echo "Checking PAM context files..."
if [ -f "CLAUDE.md" ]; then
    echo "✓ CLAUDE.md (System context)"
    if grep -q "PAM" "CLAUDE.md" 2>/dev/null; then
        echo "  Contains PAM configuration"
    fi
fi

if [ -f "INIT.md" ]; then
    echo "✓ INIT.md (PAM Memory Guide)"
    if grep -q "PAM Memory Agent Guide" "INIT.md" 2>/dev/null; then
        echo "  Contains memory organization structure"
    fi
fi

echo ""

# Final verdict
if [ $MISSING_FILES -eq 0 ]; then
    echo "========================================"
    echo "✓ ENVIRONMENT READY!"
    echo "========================================"
    echo ""
    echo "Workflow:"
    echo "1. Build: docker-compose build"
    echo "2. Run single config: docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh /benchmark_data/test_configs/config_1.yaml"
    echo "3. Run range: ./run_range_isolated.sh 1 10"
    echo "4. Run all: ./run_all_isolated.sh"
    echo ""
    echo "Processing Flow:"
    echo "- Phase 1: Claude reads INIT.md and processes event_history.json"
    echo "- Phase 2: Claude answers questions based on processed data"
    echo "- No MCP servers or Git operations required"
else
    echo "========================================"
    echo "✗ ENVIRONMENT NOT READY"
    echo "========================================"
    echo "Found $MISSING_FILES issues that need to be fixed"
fi

echo ""