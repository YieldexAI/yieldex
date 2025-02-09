#!/bin/bash

# Exit script if any command fails
set -e

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Define variables
IMAGE_NAME="data-collector"
IMAGE_TAG=${1:-"latest"}  # Use first argument as tag or "latest" if not provided

echo "Building Docker image '$IMAGE_NAME:$IMAGE_TAG'..."
docker build -t $IMAGE_NAME:$IMAGE_TAG .

echo "Docker image built successfully!" 