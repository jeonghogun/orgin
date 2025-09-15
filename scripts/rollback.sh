#!/bin/bash
set -e

# === EMERGENCY ROLLBACK SCRIPT ===
# This script rolls back the 'api' service to a previous stable Docker image tag.
# It is intended for manual execution by an operator in case of a critical deployment failure.

# !!! IMPORTANT !!!
# Before running, replace this placeholder with the actual Docker image tag
# of the last known stable version from your container registry.
PREVIOUS_IMAGE_TAG="your-repo/origin-project:previous-stable-tag"

echo "======================================================"
echo "  Starting Emergency Rollback for Origin Project API  "
echo "======================================================"
echo ""
echo "Target Image Tag: $PREVIOUS_IMAGE_TAG"
echo ""

# A simple confirmation prompt
read -p "Are you sure you want to proceed? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Rollback cancelled."
    exit 1
fi

# In a real-world scenario, you might have the image tag configured in your .env file
# and would update it here.
# Example:
# echo "Updating .env to use tag $PREVIOUS_IMAGE_TAG..."
# sed -i.bak "s/^API_IMAGE_TAG=.*/API_IMAGE_TAG=$PREVIOUS_IMAGE_TAG/" .env

echo "Step 1: Pulling the specific image tag from the registry..."
docker pull $PREVIOUS_IMAGE_TAG
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to pull image. Does the tag exist in the registry?"
    exit 1
fi
echo "Pull successful."
echo ""

echo "Step 2: Re-creating the 'api' service container with the old image..."
# This command stops and re-creates only the 'api' service, leaving the
# database and other services running. It assumes your docker-compose.yml
# references the image name that you are pulling. You may need to
# temporarily edit docker-compose.yml to point to the specific rollback tag.
# For example, change `image: your-repo/origin-project:${API_IMAGE_TAG:-latest}`
# to `image: your-repo/origin-project:previous-stable-tag`
docker-compose up -d --no-deps --force-recreate api
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to re-create the service container."
    exit 1
fi
echo "Service re-created."
echo ""

echo "======================================================"
echo "  Rollback Complete!                                "
echo "======================================================"
echo "The 'api' service should now be running the previous image."
echo "Please verify the service health immediately using 'docker-compose logs -f api'."
