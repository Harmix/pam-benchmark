#!/bin/bash
# Quick start script for MCP Docker deployment

set -e

echo "========================================"
echo "MCP Docker Quick Start"
echo "========================================"
echo ""

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed"
    echo "Please install docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check if test_configs exists
if [ ! -d "test_configs" ]; then
    echo "Warning: test_configs/ directory not found"
    echo "Creating example directory structure..."
    mkdir -p test_configs test_event_histories
    echo "Please add your config files to test_configs/"
    echo "Please add your event history files to test_event_histories/"
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
fi

# Display available configs
echo "Available configurations:"
ls -1 test_configs/*.yaml 2>/dev/null | sed 's/test_configs\///g' | sed 's/\.yaml//g' | head -5
echo ""

# Ask user which config to use
read -p "Enter config name (default: config_1): " config_name
config_name=${config_name:-config_1}

# Ask which servers to start
echo ""
echo "Which servers do you want to start?"
echo "1) Both (Slack + Linear in separate containers)"
echo "2) Slack only"
echo "3) Linear only"
echo "4) Combined (both in one container - for testing)"
read -p "Enter choice [1-4] (default: 1): " choice
choice=${choice:-1}

echo ""
echo "========================================"
echo "Building Docker images..."
echo "========================================"
docker-compose build

echo ""
echo "========================================"
echo "Starting MCP servers..."
echo "Config: $config_name"
echo "========================================"

case $choice in
    1)
        CONFIG_NAME=$config_name docker-compose up -d slack-mcp linear-mcp
        echo ""
        echo "✓ Started Slack and Linear MCP servers"
        ;;
    2)
        CONFIG_NAME=$config_name docker-compose up -d slack-mcp
        echo ""
        echo "✓ Started Slack MCP server"
        ;;
    3)
        CONFIG_NAME=$config_name docker-compose up -d linear-mcp
        echo ""
        echo "✓ Started Linear MCP server"
        ;;
    4)
        CONFIG_NAME=$config_name docker-compose --profile combined up -d mcp-combined
        echo ""
        echo "✓ Started combined MCP server"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "Servers are starting..."
echo "========================================"
sleep 2

# Show status
echo ""
docker-compose ps

echo ""
echo "========================================"
echo "Quick Start Complete!"
echo "========================================"
echo ""
echo "View logs:"
echo "  docker-compose logs -f"
echo ""
echo "Stop servers:"
echo "  docker-compose down"
echo ""
echo "Restart with different config:"
echo "  CONFIG_NAME=config_2 docker-compose up -d"
echo ""
echo "Or use Makefile shortcuts:"
echo "  make logs      # View logs"
echo "  make down      # Stop servers"
echo "  make restart   # Restart servers"
echo ""