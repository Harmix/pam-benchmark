FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy data loader
COPY data_loader.py .

# Copy ALL Python files (includes any server files regardless of naming)
COPY *.py ./

# Ensure the expected names exist (create symlinks if needed)
RUN if [ ! -f slack_mcp_server.py ] && [ -f slack_server.py ]; then \
        ln -s slack_server.py slack_mcp_server.py; \
    fi && \
    if [ ! -f linear_mcp_server.py ] && [ -f linear_server.py ]; then \
        ln -s linear_server.py linear_mcp_server.py; \
    fi

# Copy startup scripts
COPY docker-startup.py .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh docker-startup.py

# Copy test configs and event histories
COPY test_configs/ ./test_configs/
COPY test_event_histories/ ./test_event_histories/

# Expose ports for potential HTTP/SSE transports (optional)
EXPOSE 8000 8001

# Use entrypoint for flexible startup
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command (can be overridden)
CMD ["both"]