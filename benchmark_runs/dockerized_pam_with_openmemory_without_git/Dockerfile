FROM python:3.11-slim-bullseye

# Install Node.js 22, pnpm, and other dependencies
RUN apt-get update && apt-get install -y \
    curl wget git ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && npm install -g pnpm \
    && wget -q https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq \
    && chmod +x /usr/bin/yq \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Setup directories
RUN mkdir -p /workspace /mcp-servers /benchmark_data/test_configs /benchmark_data/test_event_histories /openmemory
WORKDIR /workspace

# Clone and setup OpenMemory
RUN cd /openmemory && \
    git clone https://github.com/mem0ai/mem0.git && \
    cd mem0/openmemory

# Copy and install Python dependencies for MCP servers
COPY requirements.txt /mcp-servers/
RUN pip install -q -r /mcp-servers/requirements.txt

# Install Python dependencies for OpenMemory API
RUN cd /openmemory/mem0/openmemory/api && \
    pip install -q -r requirements.txt

# Copy application files
COPY data_loader.py slack_mcp_server.py linear_mcp_server.py /mcp-servers/

# Create wrapper scripts for Slack and Linear
RUN echo '#!/bin/bash\nexport PYTHONPATH="/mcp-servers:$PYTHONPATH"\nexec python3 /mcp-servers/slack_mcp_server.py "$@"' > /mcp-servers/slack_wrapper.sh && \
    echo '#!/bin/bash\nexport PYTHONPATH="/mcp-servers:$PYTHONPATH"\nexec python3 /mcp-servers/linear_mcp_server.py "$@"' > /mcp-servers/linear_wrapper.sh && \
    chmod +x /mcp-servers/slack_wrapper.sh /mcp-servers/linear_wrapper.sh

# Copy CLAUDE.md to workspace
COPY CLAUDE.md /workspace/CLAUDE.md

# Copy benchmark data
COPY test_configs /benchmark_data/test_configs
COPY test_event_histories /benchmark_data/test_event_histories

# Copy runner script
COPY setup_and_run.sh /benchmark_data/
RUN chmod +x /benchmark_data/setup_and_run.sh

# Copy OpenMemory setup script
COPY openmemory_setup.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/openmemory_setup.sh

# Configure git
RUN echo '#!/bin/bash\n\
if [ -n "$GITHUB_TOKEN" ]; then\n\
    git config --global credential.helper store\n\
    echo "https://${GITHUB_TOKEN}@github.com" > ~/.git-credentials\n\
    git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"\n\
    echo "Git configured with GitHub token"\n\
else\n\
    echo "WARNING: GITHUB_TOKEN not set"\n\
fi\n' > /usr/local/bin/setup-git.sh && \
    chmod +x /usr/local/bin/setup-git.sh

ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/setup-git.sh && exec \"$@\"", "--"]

RUN cd /openmemory/mem0/openmemory/ui && \
    pnpm install && \
    pnpm build

# Create OpenMemory environment file
RUN mkdir -p /openmemory/mem0/openmemory/api && \
    echo 'USER=${USER_ID:-default_user}' > /openmemory/mem0/openmemory/api/.env

# Create startup script for OpenMemory services
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting OpenMemory services..."\n\
cd /openmemory/mem0/openmemory/api\n\
export USER=${USER_ID:-default_user}\n\
uvicorn main:app --host 0.0.0.0 --port 8765 &\n\
API_PID=$!\n\
cd /openmemory/mem0/openmemory/ui\n\
pnpm start &\n\
UI_PID=$!\n\
echo "OpenMemory API (PID: $API_PID) and UI (PID: $UI_PID) started"\n\
wait\n' > /usr/local/bin/start-openmemory.sh && \
    chmod +x /usr/local/bin/start-openmemory.sh

CMD ["/bin/bash"]