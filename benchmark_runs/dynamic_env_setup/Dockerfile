FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Clone the repository and checkout specific commit
RUN git clone https://github.com/openai/mle-bench.git mle_bench && \
    cd mle_bench && \
    git checkout d0f60ad0d3b2287469ac3c8ac9767330c928c980

# Install Python dependencies for MLE-Bench
WORKDIR /workspace/mle_bench
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi && \
    if [ -f setup.py ]; then pip install --no-cache-dir -e .; fi

# Install additional tools that the agent might need
RUN pip install --no-cache-dir \
    kaggle \
    openai \
    anthropic

# Set up git configuration
RUN git config --global user.email "agent@example.com" && \
    git config --global user.name "CodeAgent"

# Create directories for logs and agent work
RUN mkdir -p /workspace/logs /workspace/agent_work

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GIT_LOCAL_REPO=http://git.local:3000/pgym/mle_bench
ENV REPO_PATH=/workspace/mle_bench

WORKDIR /workspace

# Keep container running
CMD ["/bin/bash"]