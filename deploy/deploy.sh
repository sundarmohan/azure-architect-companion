#!/bin/bash

# Azure Architect Companion - EC2 Deployment Script
# This script pulls the latest Docker image and deploys using docker-compose

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_DIR="${DEPLOYMENT_DIR:-.}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKER_REGISTRY="sms300"
IMAGE_NAME="azure-architect-companion"
MAX_RETRIES=5
RETRY_INTERVAL=2

echo -e "${YELLOW}=== Azure Architect Companion Deployment ===${NC}"
echo "Image Tag: $IMAGE_TAG"
echo "Deployment Directory: $DEPLOYMENT_DIR"
echo ""

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

# Check if docker-compose.yml exists
if [ ! -f "$DEPLOYMENT_DIR/docker-compose.yml" ]; then
    echo -e "${RED}Error: docker-compose.yml not found in $DEPLOYMENT_DIR${NC}"
    exit 1
fi

# Check if .env exists
if [ ! -f "$DEPLOYMENT_DIR/.env" ]; then
    echo -e "${RED}Error: .env file not found in $DEPLOYMENT_DIR${NC}"
    echo "Please create .env file with required environment variables"
    exit 1
fi

cd "$DEPLOYMENT_DIR"

echo -e "${YELLOW}Step 1: Pulling Docker images${NC}"
if docker compose pull; then
    echo -e "${GREEN}✓ Image pulled successfully${NC}"
else
    echo -e "${RED}✗ Failed to pull image${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Starting application with database migration${NC}"
if docker compose up -d --remove-orphans; then
    echo -e "${GREEN}✓ Containers started${NC}"
else
    echo -e "${RED}✗ Failed to start containers${NC}"
    docker compose logs
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 3: Waiting for application to be ready${NC}"

# Wait for application to be ready
RETRY_COUNT=0
HEALTH_CHECK_URL="http://localhost:8001/health"

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo -n "Checking health... "
    
    if curl -f -s "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Application is ready${NC}"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo -e "${YELLOW}Retry $RETRY_COUNT/$MAX_RETRIES${NC}"
            sleep $RETRY_INTERVAL
        fi
    fi
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo -e "${RED}✗ Application health check failed${NC}"
    echo ""
    echo "Container logs:"
    docker compose logs app
    echo ""
    docker compose logs postgres
    exit 1
fi

echo ""
echo -e "${GREEN}=== Deployment Successful ===${NC}"
echo "Application is running at http://localhost:8001"
echo "Health check: $HEALTH_CHECK_URL"
echo ""
echo "Useful commands:"
echo "  docker compose ps              # Check container status"
echo "  docker compose logs app        # View application logs"
echo "  docker compose logs postgres   # View database logs"
echo "  docker compose restart         # Restart containers"
echo ""

exit 0
