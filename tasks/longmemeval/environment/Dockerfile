FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace/solution /task_data /outputs /logs/verifier

COPY tasks/longmemeval/environment/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY tasks/longmemeval/environment/run_longmemeval.py /task_data/run_longmemeval.py

COPY datasets/longmemeval/longmemeval_s_cleaned.json /task_data/data/longmemeval_s_cleaned.json

COPY tasks/longmemeval/solution/solve.sh /workspace/solution/solve.sh
RUN chmod +x /workspace/solution/solve.sh

COPY secrets.env /workspace/secrets.env

WORKDIR /workspace

ENV PYTHONPATH=/task_data

CMD ["/workspace/solution/solve.sh"]
