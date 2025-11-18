FROM python:3.11-slim

# Set memory limits and optimize container
ENV PYTHONUNBUFFERED=1
ENV DOCKER_MEMORY_LIMIT=2048m

# Install system dependencies
RUN apt-get update && apt-get install -y \
    docker.io \
    netcat-traditional \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy application files
COPY . .

# Install Python dependencies if requirements.txt exists
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Expose port range for benchmarks
EXPOSE 3000-3999

# Health check to verify port availability
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD netcat -z localhost 3000 || exit 1

# Set resource limits via labels
LABEL memory.limit="2048m"
LABEL ports.range="3000-3999"
LABEL networks.max="10"

# Run application
CMD ["python", "main.py"]