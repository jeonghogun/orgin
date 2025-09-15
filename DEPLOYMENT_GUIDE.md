# Origin Project Deployment Guide

This document provides a guide for deploying the Origin Project application to a production environment. It covers the basic setup using Docker Compose, Nginx configuration for SSL, and emergency rollback procedures.

## 1. Prerequisites

- A server with Docker and Docker Compose installed.
- A registered domain name pointing to your server's IP address.
- Port 80 and 443 open on your server's firewall.

## 2. Initial Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <project-directory>
    ```

2.  **Create Production `.env` file:**
    Copy the example environment file and populate it with your production secrets and configuration.
    ```bash
    cp .env.example .env
    nano .env
    ```
    **Crucially, for production, you must set:**
    - `AUTH_OPTIONAL=False`
    - `DEBUG=False`
    - All `POSTGRES_*`, `DB_ENCRYPTION_KEY`, and external API keys (`OPENAI_API_KEY`, etc.).
    - `CORS_ALLOWED_ORIGINS` to your frontend's domain (e.g., `https://yourapp.com`).

3.  **Build and Start the Application:**
    Use the main `docker-compose.yml` file to build and start all application services.
    ```bash
    docker-compose up --build -d
    ```
    This will start the API, database, Celery workers, and the Nginx reverse proxy. By default, Nginx listens on port 8080.

## 3. SSL/HTTPS Configuration with Nginx and Certbot

For a production environment, you must serve the application over HTTPS. The following steps describe how to use Certbot to automatically obtain and renew a free SSL certificate from Let's Encrypt.

### Step 1: Modify Nginx Configuration
The provided Nginx configuration (`config/nginx/nginx.conf`) is set up for HTTP on port 80. You will need to modify it to handle SSL.

1.  **Stop the running Nginx container** to free up port 80 for Certbot.
    ```bash
    docker-compose stop nginx
    ```
2.  **Install Certbot** on your host machine.
    ```bash
    sudo apt-get update
    sudo apt-get install certbot python3-certbot-nginx
    ```
3.  **Obtain the SSL Certificate:**
    Run Certbot and follow the prompts. It will automatically detect your domain from your Nginx configuration if it's set up correctly.
    ```bash
    sudo certbot --nginx -d yourapp.com
    ```
    Certbot will modify your `nginx.conf` to include the SSL certificate paths and set up a redirect from HTTP to HTTPS.

4.  **Restart the Nginx Container:**
    Now that SSL is configured, restart the Nginx service through Docker Compose.
    ```bash
    docker-compose up -d --no-deps nginx
    ```
    Your application should now be accessible via `https://yourapp.com`. Certbot also sets up a cron job to automatically renew the certificate.

## 4. Emergency Rollback Procedure

In case of a critical failure after a new deployment, a manual rollback to the previous stable version is necessary. This procedure assumes you are tagging your Docker images with unique version identifiers (e.g., git commit hash).

### The Rollback Script
A template script `scripts/rollback.sh` is provided to facilitate this process.

**Content of `scripts/rollback.sh`:**
```bash
#!/bin/bash
set -e

# !!! IMPORTANT !!!
# Before running, replace this with the actual tag of the last known stable image.
PREVIOUS_IMAGE_TAG="your-repo/origin-project:previous-stable-tag"

echo "Rolling back api service to image: $PREVIOUS_IMAGE_TAG"

# 1. Update the .env file if necessary to point to the old image tag
# For example, if your docker-compose.yml uses an env var for the tag:
# sed -i "s/^API_IMAGE_TAG=.*/API_IMAGE_TAG=$PREVIOUS_IMAGE_TAG/" .env

# 2. Pull the specific image tag from the registry
docker pull $PREVIOUS_IMAGE_TAG

# 3. Re-create the service container with the old image
# This command stops and re-creates only the 'api' service, leaving the
# database and other services running.
docker-compose up -d --no-deps --force-recreate api

echo ""
echo "Rollback complete. The 'api' service is now running the previous image."
echo "Please verify the service health immediately."
```

### How to Use the Rollback Script
1.  **Identify the last stable image tag.** This is the most critical step and depends on your CI/CD process and image registry.
2.  **Edit `scripts/rollback.sh`:** Update the `PREVIOUS_IMAGE_TAG` variable with the correct image tag.
3.  **Run the script:**
    ```bash
    bash scripts/rollback.sh
    ```
4.  **Verify:** Immediately check the application logs (`docker-compose logs -f api`) and test the application's core functionality to ensure the rollback was successful.
