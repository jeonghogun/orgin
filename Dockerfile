# --- Stage 1: Frontend Builder ---
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files and install dependencies
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source code
COPY app/frontend ./

# Build the static assets
RUN npm run build

# --- Stage 2: Backend Application ---
FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application code
COPY app ./app
COPY scripts ./scripts
COPY pyproject.toml .
COPY alembic ./alembic
COPY alembic.ini .

# Copy the built frontend assets from the builder stage
COPY --from=frontend-builder /app/frontend/dist /app/static

# Make the startup script executable
RUN chmod +x /app/scripts/start-prod.sh

# Set the command to run the application
CMD ["/app/scripts/start-prod.sh"]
