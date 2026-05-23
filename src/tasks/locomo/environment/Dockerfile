FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    build-essential \
    tree \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Install yq for YAML parsing (needed for PAM scripts)
RUN curl -L "https://github.com/mikefarah/yq/releases/download/v4.35.1/yq_linux_amd64" \
    -o /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq

# Install Node.js for Claude Code (needed for PAM agent)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Install Claude Code globally (for PAM agent)
RUN npm install -g @anthropic-ai/claude-code@2.0.76

# Create working directories
RUN mkdir -p /workspace/solution /task_data /outputs /task_logs /logs/verifier

# Copy requirements and install Python packages
COPY tasks/locomo/environment/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Download NLTK data required for evaluation
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"

# Copy locomo source code from task folder
COPY tasks/locomo/environment/task_eval/ /task_data/task_eval/
COPY tasks/locomo/environment/global_methods.py /task_data/global_methods.py
COPY tasks/locomo/environment/prompt_examples/ /task_data/prompt_examples/

# Copy dataset
COPY datasets/locomo/data/ /task_data/data/

# Copy the main run script
COPY tasks/locomo/environment/run_locomo.py /task_data/run_locomo.py
RUN chmod +x /task_data/run_locomo.py

# Copy PAM guide files
COPY tasks/locomo/environment/INIT.md /task_data/INIT.md
COPY tasks/locomo/environment/init.py /task_data/init.py
COPY tasks/locomo/environment/INTRO_TEMPLATE.md /task_data/INTRO_TEMPLATE.md
COPY tasks/locomo/environment/CLAUDE.md /task_data/CLAUDE.md

# Copy PAM utility scripts
COPY tasks/locomo/environment/pam_utils.py /task_data/pam_utils.py
COPY tasks/locomo/environment/pam_evaluate.py /task_data/pam_evaluate.py
COPY tasks/locomo/environment/pam_setup.sh /task_data/pam_setup.sh
COPY tasks/locomo/environment/pam_process.sh /task_data/pam_process.sh
COPY tasks/locomo/environment/pam_answer.sh /task_data/pam_answer.sh
COPY tasks/locomo/environment/run_pam_locomo.sh /task_data/run_pam_locomo.sh
RUN chmod +x /task_data/pam_*.sh /task_data/run_pam_locomo.sh

# Copy the solution script
COPY tasks/locomo/solution/solve.sh /workspace/solution/solve.sh
RUN chmod +x /workspace/solution/solve.sh

# Copy secrets.env file from project root
COPY secrets.env /workspace/secrets.env

# Copy GCP service account credentials for Vertex AI
COPY pam-agent-credentials.json /workspace/pam-agent-credentials.json

# Authenticate gcloud with service account
RUN gcloud config set project harmix-pam-rnd && \
    gcloud auth activate-service-account --key-file=/workspace/pam-agent-credentials.json

# Configure Claude Code to use Vertex AI
RUN mkdir -p /root/.claude && \
    echo '{"env":{"CLAUDE_CODE_USE_VERTEX":"1","CLOUD_ML_REGION":"europe-west1","ANTHROPIC_VERTEX_PROJECT_ID":"harmix-pam-rnd"},"permissions":{"allow":["Read(**)","Edit(**)","Write(**)","Bash(**)"]},"autoUpdaterStatus":"disabled"}' \
    > /root/.claude/settings.local.json

# Create .bashrc that sources secrets.env for interactive shells
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

# Set Python path to include task_data for imports
ENV PYTHONPATH=/task_data
ENV NODE_ENV=production

# Vertex AI environment variables for Claude Code
ENV CLAUDE_CODE_USE_VERTEX=1
ENV CLOUD_ML_REGION=europe-west1
ENV ANTHROPIC_VERTEX_PROJECT_ID=harmix-pam-rnd
ENV GOOGLE_APPLICATION_CREDENTIALS=/workspace/pam-agent-credentials.json

# Default CMD runs the solution script (Harbor mounts it at /workspace/solution/solve.sh)
CMD ["/workspace/solution/solve.sh"]
