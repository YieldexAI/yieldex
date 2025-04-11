FROM python:3.11-slim

LABEL maintainer="exectrogod@gmail.com"
LABEL description="Data collector service for Yieldex"
LABEL version="0.1.0"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy root files
COPY pyproject.toml uv.lock ./

# Copy data-collector files to new directory structure
COPY services/data_collector ./data_collector

# Also copy config.yaml to the root of data_collector directory
COPY services/data_collector/config.yaml ./data_collector/config.yaml

# Create virtual environment and install dependencies
RUN uv venv && uv sync --no-install-project

# Update PATH to use virtual environment (.venv)
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variable for logs and create directory
ENV LOG_DIR=./logs
RUN mkdir -p $LOG_DIR