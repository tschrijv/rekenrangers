#!/bin/bash

# Fail on first error
set -e

GREEN='\033[0;32m'
NC='\033[0m'

IMAGE_NAME="docker.io/rekenrangers/rekenrangers"
GIT_SHA=$(git rev-parse --short HEAD)

echo -e "${GREEN}***** Building backend image *****${NC}"
podman build -t localhost/rekenrangers:${GIT_SHA} -t localhost/rekenrangers:latest .

echo -e "${GREEN}***** Tagging image for DockerHub *****${NC}"
podman tag localhost/rekenrangers:latest ${IMAGE_NAME}:latest
podman tag localhost/rekenrangers:${GIT_SHA} ${IMAGE_NAME}:${GIT_SHA}

if [ "$1" == "push" ]; then
    echo -e "${GREEN}***** Pushing to DockerHub *****${NC}"
    podman push ${IMAGE_NAME}:latest
    podman push ${IMAGE_NAME}:${GIT_SHA}
fi
