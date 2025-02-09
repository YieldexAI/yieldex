#!/bin/bash

# Exit script if any command fails
set -e

# Run configuration check
docker run --rm \
    --env-file .env \
    --env-file .env.local \
    ${WHITE_LIST_PROTOCOLS:+"-e WHITE_LIST_PROTOCOLS=$WHITE_LIST_PROTOCOLS"} \
    ${WHITE_LIST_TOKENS:+"-e WHITE_LIST_TOKENS=$WHITE_LIST_TOKENS"} \
    data-collector:latest \
    python -c "from src.yieldex.config import validate_env_vars; assert validate_env_vars()"

echo "Configuration check passed successfully!" 