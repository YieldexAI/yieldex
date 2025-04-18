#!/bin/bash
set -e

# Load .env if exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if DOCKER_REGISTRY is set
if [ -z "$DOCKER_REGISTRY" ]; then
    echo "Error: DOCKER_REGISTRY not set. Please set it in .env file or environment"
    exit 1
fi

# Configuration
IMAGE_NAME="yieldex-data-collector"
VERSION="0.3.2"
TAG=$(date +%Y%m%d-%H%M%S)

# Create and use new buildx builder
docker buildx create --use

# Build and push production image
echo "Building and pushing image..."
docker buildx build --platform linux/amd64,linux/arm64 \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:$TAG \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:$VERSION \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:latest \
  --push \
  -f services/data_collector/Dockerfile .

echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:$TAG"
echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:$VERSION (version $VERSION)"
echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:latest"