.PHONY: help build up down logs clean restart shell test

# Default config
CONFIG ?= config_1

help:
	@echo "MCP Docker Management"
	@echo "====================="
	@echo ""
	@echo "Basic Commands:"
	@echo "  make build                    - Build Docker images"
	@echo "  make up                       - Start servers with default config (config_1)"
	@echo "  make down                     - Stop all servers"
	@echo "  make logs                     - View logs"
	@echo "  make restart                  - Restart servers"
	@echo "  make clean                    - Remove containers and images"
	@echo ""
	@echo "With Custom Config:"
	@echo "  make up CONFIG=config_vg_15   - Start with specific config"
	@echo "  make restart CONFIG=config_2  - Restart with different config"
	@echo ""
	@echo "Individual Servers:"
	@echo "  make up-slack                 - Start only Slack server"
	@echo "  make up-linear                - Start only Linear server"
	@echo "  make up-combined              - Start combined server"
	@echo ""
	@echo "Development:"
	@echo "  make shell-slack              - Shell into Slack container"
	@echo "  make shell-linear             - Shell into Linear container"
	@echo "  make test                     - Run tests in container"
	@echo ""
	@echo "Profiles:"
	@echo "  make up-crisis                - Start crisis config servers"
	@echo "  make up-vg                    - Start VG config servers"
	@echo ""
	@echo "Examples:"
	@echo "  make build"
	@echo "  make up"
	@echo "  make logs"
	@echo "  CONFIG_NAME=config_vg_15 make up"

# Build Docker images
build:
	@echo "Building MCP Docker images..."
	docker-compose build

# Start all services
up:
	@echo "Starting MCP servers with config: $(CONFIG)"
	CONFIG_NAME=$(CONFIG) docker-compose up -d slack-mcp linear-mcp

# Start only Slack
up-slack:
	@echo "Starting Slack MCP server with config: $(CONFIG)"
	CONFIG_NAME=$(CONFIG) docker-compose up -d slack-mcp

# Start only Linear
up-linear:
	@echo "Starting Linear MCP server with config: $(CONFIG)"
	CONFIG_NAME=$(CONFIG) docker-compose up -d linear-mcp

# Start combined server
up-combined:
	@echo "Starting combined MCP server with config: $(CONFIG)"
	CONFIG_NAME=$(CONFIG) docker-compose --profile combined up -d mcp-combined

# Start crisis configs
up-crisis:
	@echo "Starting crisis configuration servers..."
	docker-compose -f docker-compose.advanced.yml --profile crisis up -d

# Start VG configs
up-vg:
	@echo "Starting VG configuration servers..."
	docker-compose -f docker-compose.advanced.yml --profile vg up -d

# Stop all services
down:
	@echo "Stopping MCP servers..."
	docker-compose down
	docker-compose -f docker-compose.advanced.yml down

# View logs
logs:
	docker-compose logs -f

# View logs for specific service
logs-slack:
	docker-compose logs -f slack-mcp

logs-linear:
	docker-compose logs -f linear-mcp

# Restart services
restart:
	@echo "Restarting MCP servers with config: $(CONFIG)"
	CONFIG_NAME=$(CONFIG) docker-compose restart

# Clean up
clean:
	@echo "Cleaning up Docker resources..."
	docker-compose down -v --remove-orphans
	docker-compose -f docker-compose.advanced.yml down -v --remove-orphans
	docker image rm $$(docker images -q '*mcp*' 2>/dev/null) 2>/dev/null || true

# Shell access
shell-slack:
	docker exec -it slack-mcp-server /bin/bash

shell-linear:
	docker exec -it linear-mcp-server /bin/bash

# Run tests
test:
	docker-compose run --rm slack-mcp python test_data_loader.py

# Check container status
status:
	@echo "MCP Container Status:"
	@docker ps -a --filter "name=mcp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# View available configs
list-configs:
	@echo "Available configurations:"
	@ls -1 test_configs/*.yaml | sed 's/test_configs\///g' | sed 's/\.yaml//g' | sort