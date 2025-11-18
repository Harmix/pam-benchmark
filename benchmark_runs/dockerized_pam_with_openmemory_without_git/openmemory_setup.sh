#!/bin/bash

case "$1" in
    start)
        USER_ID=${2:-default_user}
        CONFIG_NAME=${3:-default}

        echo "Starting OpenMemory for user: $USER_ID, config: $CONFIG_NAME"

        # Set environment
        export USER_ID="$USER_ID"
        export OPENAI_API_KEY="${OPENAI_API_KEY}"

        # Create memory directory
        mkdir -p "/openmemory/memories/${CONFIG_NAME}/${USER_ID}"

        # Create API .env
        cat > /openmemory/mem0/openmemory/api/.env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
USER=${USER_ID}
EOF

        # Create UI .env
        cat > /openmemory/mem0/openmemory/ui/.env <<EOF
NEXT_PUBLIC_API_URL=http://localhost:8765
NEXT_PUBLIC_USER_ID=${USER_ID}
EOF

        # Start API
        cd /openmemory/mem0/openmemory/api
        nohup uvicorn main:app --host 0.0.0.0 --port 8765 > /tmp/openmemory-api.log 2>&1 &
        echo $! > /tmp/openmemory-api.pid

        # Start UI
        cd /openmemory/mem0/openmemory/ui
        nohup pnpm start > /tmp/openmemory-ui.log 2>&1 &
        echo $! > /tmp/openmemory-ui.pid

        echo "OpenMemory started. Waiting for services..."
        sleep 8
        ;;

    stop)
        echo "Stopping OpenMemory..."
        if [ -f /tmp/openmemory-api.pid ]; then
            kill $(cat /tmp/openmemory-api.pid) 2>/dev/null || true
            rm /tmp/openmemory-api.pid
        fi
        if [ -f /tmp/openmemory-ui.pid ]; then
            kill $(cat /tmp/openmemory-ui.pid) 2>/dev/null || true
            rm /tmp/openmemory-ui.pid
        fi
        pkill -f "uvicorn main:app" 2>/dev/null || true
        pkill -f "pnpm start" 2>/dev/null || true
        echo "OpenMemory stopped"
        ;;

    status)
        echo "=== OpenMemory Status ==="
        if [ -f /tmp/openmemory-api.pid ] && kill -0 $(cat /tmp/openmemory-api.pid) 2>/dev/null; then
            echo "API: Running (PID: $(cat /tmp/openmemory-api.pid))"
            curl -s http://localhost:8765/health || echo "API not responding"
        else
            echo "API: Not running"
        fi

        if [ -f /tmp/openmemory-ui.pid ] && kill -0 $(cat /tmp/openmemory-ui.pid) 2>/dev/null; then
            echo "UI: Running (PID: $(cat /tmp/openmemory-ui.pid))"
        else
            echo "UI: Not running"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|status} [user_id] [config_name]"
        exit 1
        ;;
esac