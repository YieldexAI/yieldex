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
VERSION="0.3"
TAG=$(date +%Y%m%d-%H%M%S)

# Create and use new buildx builder
docker buildx create --use

# Build and push production image
echo "Building production image..."
docker buildx build --platform linux/amd64,linux/arm64 \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:$TAG \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:$VERSION \
  --push \
  -f Dockerfile-data-collector .

# Build and push test image
echo "Building test image..."
docker buildx build --platform linux/amd64,linux/arm64 \
  -t $DOCKER_REGISTRY/$IMAGE_NAME:test \
  --push \
  -f Dockerfile-test .

echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:$TAG (production)"
echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:$VERSION (version $VERSION)"
echo "Built and pushed: $DOCKER_REGISTRY/$IMAGE_NAME:test (test)" 