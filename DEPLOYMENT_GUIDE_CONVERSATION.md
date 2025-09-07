# Conversation System Deployment Guide

This guide provides comprehensive instructions for deploying the GPT-style conversation system in various environments.

## 📋 Prerequisites

### System Requirements
- **CPU**: 4+ cores (8+ recommended for production)
- **RAM**: 8GB+ (16GB+ recommended for production)
- **Storage**: 100GB+ SSD (1TB+ recommended for production)
- **Network**: Stable internet connection for LLM API calls

### Software Requirements
- **Docker**: 20.10+ with Docker Compose 2.0+
- **Python**: 3.11+ (for local development)
- **Node.js**: 18+ (for frontend development)
- **PostgreSQL**: 15+ with pgvector extension
- **Redis**: 7.0+

## 🚀 Quick Start (Docker Compose)

### 1. Clone and Setup
```bash
# Clone repository
git clone <repository-url>
cd orgin

# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env
```

### 2. Configure Environment
```bash
# Required environment variables
DATABASE_URL=postgresql://postgres:password@db:5432/orgin
REDIS_URL=redis://redis:6379

# LLM API Keys (at least one required)
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GEMINI_API_KEY=AI-your-gemini-key

# Feature Configuration
ENABLE_CONVERSATION=true
DAILY_TOKEN_BUDGET=200000
DAILY_COST_BUDGET=50.0

# Security
SECRET_KEY=your-secret-key-here
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://yourdomain.com
```

### 3. Start Services
```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f api
```

### 4. Initialize Database
```bash
# Run database migrations
docker-compose exec api alembic upgrade head

# Verify database setup
docker-compose exec db psql -U postgres -d orgin -c "\dt"
```

### 5. Verify Deployment
```bash
# Check API health
curl http://localhost:8000/api/health

# Check frontend
curl http://localhost:5173

# Test conversation endpoint
curl -X POST http://localhost:8000/api/convo/models \
  -H "Authorization: Bearer test-token"
```

## 🏭 Production Deployment

### 1. Production Docker Compose
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  api:
    build: 
      context: .
      dockerfile: Dockerfile.prod
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - SECRET_KEY=${SECRET_KEY}
      - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS}
      - ENVIRONMENT=production
    depends_on:
      - db
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: pgvector/pgvector:pg15
    environment:
      - POSTGRES_DB=orgin
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./config/nginx/nginx.prod.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 2. Production Environment Setup
```bash
# Create production environment file
cat > .env.prod << EOF
# Database
DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@db:5432/orgin
DB_PASSWORD=your-secure-db-password

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
REDIS_PASSWORD=your-secure-redis-password

# LLM API Keys
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GEMINI_API_KEY=AI-your-gemini-key

# Security
SECRET_KEY=your-very-secure-secret-key
CORS_ALLOWED_ORIGINS=https://yourdomain.com

# Production Settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Feature Flags
ENABLE_CONVERSATION=true
DAILY_TOKEN_BUDGET=500000
DAILY_COST_BUDGET=100.0
ENABLE_MONITORING=true
EOF
```

### 3. Deploy to Production
```bash
# Deploy with production configuration
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head

# Verify deployment
curl https://yourdomain.com/api/health
```

## ☸️ Kubernetes Deployment

### 1. Namespace and ConfigMap
```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: conversation-system

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: conversation-config
  namespace: conversation-system
data:
  DATABASE_URL: "postgresql://postgres:password@postgres-service:5432/orgin"
  REDIS_URL: "redis://redis-service:6379"
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
```

### 2. Secrets
```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: conversation-secrets
  namespace: conversation-system
type: Opaque
data:
  OPENAI_API_KEY: <base64-encoded-key>
  ANTHROPIC_API_KEY: <base64-encoded-key>
  GEMINI_API_KEY: <base64-encoded-key>
  SECRET_KEY: <base64-encoded-secret>
  DB_PASSWORD: <base64-encoded-password>
```

### 3. Database Deployment
```yaml
# k8s/postgres-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: conversation-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg15
        env:
        - name: POSTGRES_DB
          value: "orgin"
        - name: POSTGRES_USER
          value: "postgres"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: conversation-secrets
              key: DB_PASSWORD
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: conversation-system
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### 4. API Deployment
```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: conversation-api
  namespace: conversation-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: conversation-api
  template:
    metadata:
      labels:
        app: conversation-api
    spec:
      containers:
      - name: api
        image: your-registry/conversation-api:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: conversation-config
        - secretRef:
            name: conversation-secrets
        livenessProbe:
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: conversation-api-service
  namespace: conversation-system
spec:
  selector:
    app: conversation-api
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### 5. Deploy to Kubernetes
```bash
# Apply all configurations
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -n conversation-system
kubectl get services -n conversation-system

# Run database migrations
kubectl exec -it deployment/conversation-api -n conversation-system -- alembic upgrade head

# Check logs
kubectl logs -f deployment/conversation-api -n conversation-system
```

## 🔧 Configuration

### Nginx Configuration
```nginx
# config/nginx/nginx.prod.conf
events {
    worker_connections 1024;
}

http {
    upstream api_backend {
        server api:8000;
    }

    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # API routes
        location /api/ {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # SSE specific settings
            location /api/convo/messages/ {
                proxy_pass http://api_backend;
                proxy_http_version 1.1;
                proxy_set_header Connection "";
                proxy_buffering off;
                proxy_cache off;
                proxy_set_header Cache-Control no-cache;
                proxy_read_timeout 300s;
                proxy_send_timeout 300s;
            }
        }

        # Frontend
        location / {
            root /usr/share/nginx/html;
            index index.html;
            try_files $uri $uri/ /index.html;
        }

        # Static files
        location /static/ {
            alias /usr/share/nginx/html/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### SSL Certificate Setup
```bash
# Using Let's Encrypt
certbot certonly --standalone -d yourdomain.com

# Copy certificates to nginx
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./ssl/key.pem
```

## 📊 Monitoring Setup

### Prometheus Configuration
```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'conversation-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/api/metrics'
    scrape_interval: 30s

  - job_name: 'postgres'
    static_configs:
      - targets: ['db:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
```

### Grafana Dashboard
```json
{
  "dashboard": {
    "title": "Conversation System",
    "panels": [
      {
        "title": "API Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "LLM Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(llm_requests_total[5m])) by (model)"
          }
        ]
      }
    ]
  }
}
```

## 🔒 Security Hardening

### 1. Network Security
```bash
# Firewall rules
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw deny 5432/tcp  # PostgreSQL (internal only)
ufw deny 6379/tcp  # Redis (internal only)
ufw enable
```

### 2. Database Security
```sql
-- Create application user
CREATE USER conversation_app WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE orgin TO conversation_app;
GRANT USAGE ON SCHEMA public TO conversation_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO conversation_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO conversation_app;
```

### 3. Container Security
```dockerfile
# Dockerfile.prod
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Change ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Start application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Database Connection Issues
```bash
# Check database connectivity
docker-compose exec api python -c "
import psycopg2
conn = psycopg2.connect('postgresql://postgres:password@db:5432/orgin')
print('Database connected successfully')
"

# Check database logs
docker-compose logs db
```

#### 2. Redis Connection Issues
```bash
# Test Redis connection
docker-compose exec api python -c "
import redis
r = redis.Redis(host='redis', port=6379, db=0)
print('Redis connected:', r.ping())
"

# Check Redis logs
docker-compose logs redis
```

#### 3. LLM API Issues
```bash
# Test OpenAI API
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Check API logs
docker-compose logs api | grep -i "openai\|anthropic\|gemini"
```

#### 4. Performance Issues
```bash
# Check resource usage
docker stats

# Check database performance
docker-compose exec db psql -U postgres -d orgin -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
"
```

### Log Analysis
```bash
# View application logs
docker-compose logs -f api

# Filter error logs
docker-compose logs api | grep -i error

# Monitor real-time logs
tail -f logs/app.log | grep -E "(ERROR|WARNING)"
```

## 📈 Performance Tuning

### Database Optimization
```sql
-- Analyze table statistics
ANALYZE;

-- Update table statistics
VACUUM ANALYZE;

-- Check index usage
SELECT schemaname, tablename, attname, n_distinct, correlation 
FROM pg_stats 
WHERE tablename IN ('conversation_messages', 'conversation_threads');

-- Add missing indexes
CREATE INDEX CONCURRENTLY idx_conversation_messages_user_timestamp 
ON conversation_messages(user_id, timestamp DESC);
```

### Application Optimization
```python
# app/config/settings.py
class Settings:
    # Database connection pool
    DATABASE_POOL_SIZE = 20
    DATABASE_MAX_OVERFLOW = 30
    
    # Redis connection pool
    REDIS_POOL_SIZE = 10
    
    # LLM request timeout
    LLM_REQUEST_TIMEOUT = 30
    
    # SSE timeout
    SSE_TIMEOUT = 300
```

## 🔄 Backup and Recovery

### Database Backup
```bash
# Create backup
docker-compose exec db pg_dump -U postgres orgin > backup_$(date +%Y%m%d_%H%M%S).sql

# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T db pg_dump -U postgres orgin > $BACKUP_DIR/backup_$DATE.sql
gzip $BACKUP_DIR/backup_$DATE.sql

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

### Recovery
```bash
# Restore from backup
docker-compose exec -T db psql -U postgres orgin < backup_20240107_120000.sql

# Verify restoration
docker-compose exec db psql -U postgres -d orgin -c "SELECT COUNT(*) FROM conversation_threads;"
```

## 📞 Support

### Health Checks
```bash
# API health
curl http://localhost:8000/api/health

# Database health
docker-compose exec db pg_isready -U postgres

# Redis health
docker-compose exec redis redis-cli ping
```

### Monitoring Endpoints
- `/api/health` - System health status
- `/api/metrics/summary` - System metrics
- `/api/metrics/system` - Resource usage
- `/api/metrics/llm` - LLM usage statistics

### Contact Information
- **Documentation**: [docs.yourcompany.com](https://docs.yourcompany.com)
- **Support Email**: support@yourcompany.com
- **GitHub Issues**: [github.com/yourorg/orgin/issues](https://github.com/yourorg/orgin/issues)
- **Slack Channel**: #conversation-system

---

This deployment guide covers the essential steps for deploying the conversation system. For additional support or advanced configurations, please refer to the documentation or contact the support team.
