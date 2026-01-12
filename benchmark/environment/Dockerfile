FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    build-essential \
    tree \
    && rm -rf /var/lib/apt/lists/*

# Install yq for YAML parsing
RUN curl -L "https://github.com/mikefarah/yq/releases/download/v4.35.1/yq_linux_amd64" \
    -o /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq

# Install Node.js for Claude Code
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Install Claude Code globally (version 2.0.76)
RUN npm install -g @anthropic-ai/claude-code@2.0.76

# Create working directories
RUN mkdir -p /workspace/unsorted /workspace/logs /benchmark_data /logs/verifier

# Copy benchmark data from task root
# Harbor uses task root as build context, so paths are relative to task root
COPY test_configs/ /benchmark_data/test_configs/
COPY test_event_histories/ /benchmark_data/test_event_histories/
COPY setup_and_run.sh /benchmark_data/setup_and_run.sh
RUN chmod +x /benchmark_data/setup_and_run.sh

# Copy PAM guide files to benchmark_data
COPY INIT.md /benchmark_data/INIT.md
COPY init.py /benchmark_data/init.py
COPY INTRO_TEMPLATE.md /benchmark_data/INTRO_TEMPLATE.md
COPY CLAUDE.md /benchmark_data/CLAUDE.md

WORKDIR /workspace

# Set environment variables
ENV NODE_ENV=production

CMD ["/bin/bash"]
