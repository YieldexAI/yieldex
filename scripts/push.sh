#!/bin/bash

# Exit script if any command fails
set -e

# Define variables
IMAGE_NAME="data-collector"
IMAGE_TAG=${1:-"latest"}  # Use first argument as tag or "latest" if not provided
DOCKER_HUB_USERNAME="your-username"  # Замените на ваш username в DockerHub

# Login to Docker Hub (требуется только один раз)
# docker login

# Tag the image for Docker Hub
docker tag $IMAGE_NAME:$IMAGE_TAG $DOCKER_HUB_USERNAME/$IMAGE_NAME:$IMAGE_TAG

# Push to Docker Hub
echo "Pushing image to Docker Hub..."
docker push $DOCKER_HUB_USERNAME/$IMAGE_NAME:$IMAGE_TAG

echo "Image successfully pushed to Docker Hub!" 