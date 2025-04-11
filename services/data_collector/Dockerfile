FROM python:3.11-slim

LABEL maintainer="exectrogod@gmail.com"
LABEL description="Data collector service for Yieldex (cron edition)"
LABEL version="0.1.1"

ENV DEBIAN_FRONTEND=noninteractive

# ----- system packages -----
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron procps \
    && rm -rf /var/lib/apt/lists/*

# ----- Python/uv -----
RUN pip install --no-cache-dir uv

# ----- working directory -----
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/data_collector ./data_collector
COPY services/data_collector/config.yaml ./data_collector/config.yaml

# ----- virtual environment and dependencies -----
RUN uv venv \
 && uv pip install -e data_collector

ENV PATH="/app/.venv/bin:$PATH"

# ----- log directory -----
ENV LOG_DIR=/app/logs
RUN mkdir -p $LOG_DIR

# ----- wrapper script -----
RUN printf '%s\n' \
    '#!/bin/sh' \
    'exec /app/.venv/bin/python -m yieldex_data_collector.collector' \
    > /usr/local/bin/run-collector && chmod +x /usr/local/bin/run-collector

# ----- Default cron schedule (can be overridden) -----
ENV CRON_SCHEDULE="*/30 * * * *"

# ----- create entrypoint script -----
RUN printf '%s\n' \
    '#!/bin/sh' \
    'echo "Setting up cron job with schedule: $CRON_SCHEDULE"' \
    'echo "$CRON_SCHEDULE root /usr/local/bin/run-collector >> /app/logs/collector_\$(date +\\%Y\\%m\\%d).log 2>&1" > /etc/cron.d/collector-cron' \
    'chmod 0644 /etc/cron.d/collector-cron' \
    'crontab /etc/cron.d/collector-cron' \
    'echo "Cron job configured. Starting cron daemon..."' \
    'exec cron -f' \
    > /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# ----- startup -----
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]