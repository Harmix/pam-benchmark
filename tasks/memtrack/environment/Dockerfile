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

# Install Python packages needed for evaluation script
COPY tasks/memtrack/environment/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create working directories
RUN mkdir -p /workspace/unsorted /workspace/logs /task_data /logs/verifier

# Copy dataset from datasets folder at project root
# Build context is now the project root, so we can access datasets directly
# This avoids copying datasets for each execution
COPY datasets/memtrack/test_configs/ /task_data/test_configs/
COPY datasets/memtrack/test_event_histories/ /task_data/test_event_histories/
COPY tasks/memtrack/environment/setup_and_run.sh /task_data/setup_and_run.sh
RUN chmod +x /task_data/setup_and_run.sh

# Copy PAM guide files to task_data (paths relative to project root)
COPY tasks/memtrack/environment/INIT.md /task_data/INIT.md
COPY tasks/memtrack/environment/init.py /task_data/init.py
COPY tasks/memtrack/environment/INTRO_TEMPLATE.md /task_data/INTRO_TEMPLATE.md
COPY tasks/memtrack/environment/CLAUDE.md /task_data/CLAUDE.md

# Copy stub parser script
COPY tasks/memtrack/environment/parse_oracle_stub.py /task_data/parse_oracle_stub.py
RUN chmod +x /task_data/parse_oracle_stub.py

# Copy debug oracle files for DEBUG/stub mode
COPY agents/debug/ /task_data/debug/

# Copy secrets.env file from project root
COPY secrets.env /workspace/secrets.env

# Create .bashrc that sources secrets.env for interactive shells
# This ensures environment variables are available even if Harbor starts a new shell session
RUN echo '' >> /root/.bashrc && \
    echo '# Source secrets.env for environment variables' >> /root/.bashrc && \
    echo 'if [ -f /workspace/secrets.env ]; then' >> /root/.bashrc && \
    echo '  set -a' >> /root/.bashrc && \
    echo '  source /workspace/secrets.env' >> /root/.bashrc && \
    echo '  set +a' >> /root/.bashrc && \
    echo 'fi' >> /root/.bashrc

# Also create .bash_profile for login shells (sources .bashrc)
RUN echo 'if [ -f ~/.bashrc ]; then . ~/.bashrc; fi' >> /root/.bash_profile

WORKDIR /workspace

# Set environment variables
ENV NODE_ENV=production

# Default CMD runs solution script (Harbor mounts it at /workspace/solution/solve.sh)
# Harbor will execute this when running tasks
CMD ["/workspace/solution/solve.sh"]
