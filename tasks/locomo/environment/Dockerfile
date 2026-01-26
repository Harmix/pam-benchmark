FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create working directories
RUN mkdir -p /workspace/solution /task_data /outputs /logs/verifier

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

# Copy the run script
COPY tasks/locomo/environment/run_locomo.py /task_data/run_locomo.py
RUN chmod +x /task_data/run_locomo.py

# Copy the solution script
COPY tasks/locomo/solution/solve.sh /workspace/solution/solve.sh
RUN chmod +x /workspace/solution/solve.sh

# Copy secrets.env file from project root
COPY secrets.env /workspace/secrets.env

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

# Default CMD runs the solution script (Harbor mounts it at /workspace/solution/solve.sh)
CMD ["/workspace/solution/solve.sh"]
