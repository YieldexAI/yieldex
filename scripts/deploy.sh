#!/bin/bash

# Exit script if any command fails
set -e

# Validate required environment variables
validate_env() {
    local missing_vars=()
    
    # Check RPC URLs
    for network in "POLYGON" "MANTLE" "ETHEREUM" "ARBITRUM" "OPTIMISM" "BASE" "AVALANCHE"; do
        if [ -z "${!network}_RPC_URL" ]; then
            missing_vars+=("${network}_RPC_URL")
        fi
    done
    
    # Check Supabase
    if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
        missing_vars+=("SUPABASE_URL/KEY")
    fi
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo "Error: Missing required environment variables:"
        printf '%s\n' "${missing_vars[@]}"
        exit 1
    fi
}

# Validate environment before deploying
validate_env

# Define variables
IMAGE_NAME="data-collector"
IMAGE_TAG=${1:-"latest"}  # Use first argument as tag or "latest" if not provided
CONTAINER_NAME="data-collector"

# Create logs directory if it doesn't exist
mkdir -p ./logs

# Check if a container with the same name is already running
if [ $(docker ps -q -f name=$CONTAINER_NAME) ]; then
    echo "Container '$CONTAINER_NAME' is running. Stopping it..."
    docker stop $CONTAINER_NAME
fi

# Remove the container if it exists
if [ $(docker ps -aq -f name=$CONTAINER_NAME) ]; then
    echo "Removing existing container '$CONTAINER_NAME'..."
    docker rm $CONTAINER_NAME
fi

# Run the container
echo "Starting container '$CONTAINER_NAME' from image '$IMAGE_NAME:$IMAGE_TAG'..."

# Примеры запуска:
# ./deploy.sh                                                           # использовать значения по умолчанию
# WHITE_LIST_PROTOCOLS="aave-v3,compound-v3" ./deploy.sh               # только определенные протоколы
# WHITE_LIST_TOKENS="USDT,USDC" ./deploy.sh                           # только определенные токены
# WHITE_LIST_PROTOCOLS="aave-v3" WHITE_LIST_TOKENS="USDT" ./deploy.sh # изменить оба списка

docker run -d \
    --name $CONTAINER_NAME \
    --env-file .env \
    --env-file .env.local \
    ${WHITE_LIST_PROTOCOLS:+"-e WHITE_LIST_PROTOCOLS=$WHITE_LIST_PROTOCOLS"} \
    ${WHITE_LIST_TOKENS:+"-e WHITE_LIST_TOKENS=$WHITE_LIST_TOKENS"} \
    -v "$(pwd)/logs:/app/logs" \
    --restart unless-stopped \
    --health-cmd="python -c 'from src.yieldex.data_collector import fetch_pools; assert fetch_pools()'" \
    --health-interval=30s \
    --health-timeout=10s \
    --health-retries=3 \
    $IMAGE_NAME:$IMAGE_TAG

echo "Container '$CONTAINER_NAME' is running."

# Monitor container health
echo "Monitoring container health..."
sleep 5
docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME 