# Production Deployment Guide

This document outlines the process for deploying the Origin project to a production environment.

## 1. Overview

The production environment is orchestrated using Docker Compose. It consists of several services:
- `nginx`: The public-facing reverse proxy.
- `api`: The main FastAPI web application.
- `worker-default`, `worker-high-priority`, `worker-low-priority`: Celery workers for different task queues.
- `pgbouncer`: A connection pooler for the database.
- `db`: The PostgreSQL database.
- `redis`: The Redis server for caching, Celery, and WebSocket Pub/Sub.

## 2. Prerequisites

- A server with Docker and Docker Compose installed.
- A configured secrets management system (e.g., GitHub Actions Secrets, HashiCorp Vault, AWS Secrets Manager).
- An external PostgreSQL database and Redis instance are recommended for a true production setup, but this guide will use the Docker Compose services.

## 3. Configuration & Secrets Management

**Do not use the `.env` file for production!** It is for local development only. Production secrets must be supplied to the environment securely.

### Required Environment Variables:

The following environment variables must be set for the `api` and `worker` services:

- `DATABASE_URL`: The full connection string for the application to connect to **PgBouncer**.
  - *Format*: `postgresql://<user>:<password>@pgbouncer:6432/<dbname>`
- `DB_ENCRYPTION_KEY`: A strong, secret key for `pgcrypto` field encryption.
- `REDIS_URL`: The connection URL for the Redis server.
- `OPENAI_API_KEY`: Your secret key for the OpenAI API.
- `GOOGLE_API_KEY`: (Optional) Your Google API key for custom search.
- `GOOGLE_CSE_ID`: (Optional) Your Google Custom Search Engine ID.

### Example: Using a `.env` file with Docker Compose

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```
2. **Edit `.env`** and fill in the required secrets.
   - `DATABASE_URL` should point to the `pgbouncer` service.
   - `REDIS_URL` should point to the `redis` service.

## 4. Building and Running the Application

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd origin
   ```

2. **Set up the `.env` file** as described in the section above.

3. **Build and start the services:**
   The `--build` flag will force Docker to rebuild the images using the `Dockerfile`. The `-d` flag runs the containers in detached mode.
   ```bash
   docker-compose up -d --build
   ```

4. **Initializing the Database:**
   The first time you run the application, the PostgreSQL container will be initialized by Docker Compose using the `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` variables. The schema defined in `app/db/schema.sql` needs to be applied **after** the container is up and healthy.

   You can apply the schema with the following command:
   ```bash
   docker-compose exec -T db psql -U user -d origin_db < app/db/schema.sql
   ```
   *(Note: The user/db values here match the defaults in the `docker-compose.yml` `db` service. If you change them there, change them here as well.)*

## 5. CI/CD Pipeline

The repository includes a GitHub Actions workflow in `.github/workflows/ci.yml`. This pipeline automatically performs linting and runs the full test suite on every push and pull request to the `main` branch.

For a full Continuous Deployment setup, this pipeline can be extended to include a "Deploy" step that runs on a merge to `main`. This step would typically:
1. Build and push the Docker image to a container registry (e.g., Docker Hub, GHCR, ECR).
2. SSH into the production server.
3. Run `docker-compose pull` to pull the new image.
4. Run `docker-compose up -d` to restart the services with the new image.
