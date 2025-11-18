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

# Setup directories - workspace for Claude, benchmark_data outside workspace
RUN mkdir -p /workspace /mcp-servers /benchmark_data/test_configs /benchmark_data/test_event_histories
WORKDIR /workspace

# Copy and install Python dependencies
COPY requirements.txt /mcp-servers/
RUN pip install -q -r /mcp-servers/requirements.txt

# Copy application files
COPY data_loader.py slack_mcp_server.py linear_mcp_server.py /mcp-servers/

# Create wrapper scripts
RUN echo '#!/bin/bash\nexport PYTHONPATH="/mcp-servers:$PYTHONPATH"\nexec python3 /mcp-servers/slack_mcp_server.py "$@"' > /mcp-servers/slack_wrapper.sh && \
    echo '#!/bin/bash\nexport PYTHONPATH="/mcp-servers:$PYTHONPATH"\nexec python3 /mcp-servers/linear_mcp_server.py "$@"' > /mcp-servers/linear_wrapper.sh && \
    chmod +x /mcp-servers/slack_wrapper.sh /mcp-servers/linear_wrapper.sh

# Copy CLAUDE.md to workspace - Claude Code will read it from here
COPY CLAUDE.md /workspace/CLAUDE.md

# Copy benchmark data outside workspace to prevent cheating
COPY test_configs /benchmark_data/test_configs
COPY test_event_histories /benchmark_data/test_event_histories

# Copy runner script
COPY setup_and_run.sh /benchmark_data/
RUN chmod +x /benchmark_data/setup_and_run.sh

# Configure git to use GitHub token from environment variable
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

# Run git setup on container start
ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/setup-git.sh && exec \"$@\"", "--"]

CMD ["/bin/bash"]