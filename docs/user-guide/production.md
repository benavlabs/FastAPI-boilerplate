# Production Deployment

This guide covers deploying the FastAPI boilerplate to production with proper performance, security, and reliability configurations.

## Production Architecture

The recommended production setup uses:

- **Gunicorn** - WSGI server managing Uvicorn workers
- **Uvicorn Workers** - ASGI server handling FastAPI requests
- **NGINX** - Reverse proxy and load balancer
- **PostgreSQL** - Production database
- **Redis** - Caching and background tasks
- **Docker** - Containerization

## Environment Configuration

### Production Environment Variables

Update your `.env` file for production:

```bash
# ------------- environment -------------
ENVIRONMENT="production"

# ------------- app settings -------------
APP_NAME="Your Production App"
DEBUG=false

# ------------- database -------------
POSTGRES_USER="prod_user"
POSTGRES_PASSWORD="secure_production_password"
POSTGRES_SERVER="db"  # or your database host
POSTGRES_PORT=5432
POSTGRES_DB="prod_database"

# ------------- redis -------------
REDIS_CACHE_HOST="redis"
REDIS_CACHE_PORT=6379
REDIS_QUEUE_HOST="redis"
REDIS_QUEUE_PORT=6379
REDIS_RATE_LIMIT_HOST="redis"
REDIS_RATE_LIMIT_PORT=6379

# ------------- security -------------
SECRET_KEY="your-super-secure-secret-key-generate-with-openssl"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ------------- logging -------------
LOG_LEVEL="INFO"
```

### Docker Configuration

#### Production Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /code
USER app

# Production command with Gunicorn
CMD ["uv", "run", "gunicorn", "src.app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

#### Production Docker Compose

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - ./src/.env
    depends_on:
      - db
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  worker:
    build: .
    command: uv run arq src.app.core.worker.settings.WorkerSettings
    env_file:
      - ./src/.env
    depends_on:
      - db
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2

  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

## Gunicorn Configuration

### Basic Gunicorn Setup

Create `gunicorn.conf.py`:

```python
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Restart workers after this many requests, with up to 50 jitter
preload_app = True

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "fastapi-boilerplate"

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (if terminating SSL at application level)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Worker timeout
timeout = 30
keepalive = 2

# Memory management
max_requests = 1000
max_requests_jitter = 50
preload_app = True
```

### Running with Gunicorn

```bash
# Basic command
uv run gunicorn src.app.main:app -w 4 -k uvicorn.workers.UvicornWorker

# With configuration file
uv run gunicorn src.app.main:app -c gunicorn.conf.py

# With specific bind address
uv run gunicorn src.app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## NGINX Configuration

### Single Server Setup

Create `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream fastapi_backend {
        server web:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;

        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # Gzip compression
        gzip on;
        gzip_vary on;
        gzip_min_length 10240;
        gzip_proxied expired no-cache no-store private must-revalidate auth;
        gzip_types
            text/plain
            text/css
            text/xml
            text/javascript
            application/javascript
            application/xml+rss
            application/json;

        # Rate limiting
        limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

        location / {
            limit_req zone=api burst=20 nodelay;
            
            proxy_pass http://fastapi_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
            
            # Buffer settings
            proxy_buffering on;
            proxy_buffer_size 8k;
            proxy_buffers 8 8k;
        }

        # Health check endpoint (no rate limiting)
        location /health {
            proxy_pass http://fastapi_backend;
            proxy_set_header Host $host;
            access_log off;
        }

        # Static files (if any)
        location /static/ {
            alias /code/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### Simple Single Server (default.conf)

For basic production setup, create `default.conf`:

```nginx
# ---------------- Running With One Server ----------------
server {
    listen 80;

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Load Balancing Multiple Servers  

For horizontal scaling with multiple FastAPI instances:

```nginx
# ---------------- To Run with Multiple Servers ----------------
upstream fastapi_app {
    server fastapi1:8000;  # Replace with actual server names
    server fastapi2:8000;
    # Add more servers as needed
}

server {
    listen 80;

    location / {
        proxy_pass http://fastapi_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Advanced Load Balancing

For production with advanced features:

```nginx
upstream fastapi_backend {
    least_conn;
    server web1:8000 weight=3;
    server web2:8000 weight=2;
    server web3:8000 weight=1;
    
    # Health checks
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    location / {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Connection settings for load balancing
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

### SSL Certificate Setup

#### Using Let's Encrypt (Certbot)

```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal (add to crontab)
0 2 * * 1 /usr/bin/certbot renew --quiet
```

#### Manual SSL Setup

```bash
# Generate self-signed certificate (development only)
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/key.pem \
    -out nginx/ssl/cert.pem
```

## Production Best Practices

### Database Optimization

#### PostgreSQL Configuration

```sql
-- Optimize PostgreSQL for production
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
SELECT pg_reload_conf();
```

#### Connection Pooling

```python
# src/app/core/db/database.py
from sqlalchemy.ext.asyncio import create_async_engine

# Production database settings
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Disable in production
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

### Redis Configuration

#### Redis Production Settings

```bash
# redis.conf adjustments
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### Application Optimization

#### Logging Configuration

```python
# src/app/core/config.py
import logging
from pythonjsonlogger import jsonlogger

def setup_production_logging():
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logHandler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.addHandler(logHandler)
    logger.setLevel(logging.INFO)
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```

#### Performance Monitoring

```python
# src/app/middleware/monitoring.py
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log slow requests
        if process_time > 1.0:
            logger.warning(f"Slow request: {request.method} {request.url} - {process_time:.2f}s")
        
        return response
```

### Security Configuration

#### Environment Security

```python
# src/app/core/config.py
class ProductionSettings(Settings):
    # Hide docs in production
    ENVIRONMENT: str = "production"
    
    # Security settings
    SECRET_KEY: str = Field(..., min_length=32)
    ALLOWED_HOSTS: list[str] = ["your-domain.com", "api.your-domain.com"]
    
    # Database security
    POSTGRES_PASSWORD: str = Field(..., min_length=16)
    
    class Config:
        case_sensitive = True
```

#### Rate Limiting

```python
# Adjust rate limits for production
DEFAULT_RATE_LIMIT_LIMIT = 100  # requests per period
DEFAULT_RATE_LIMIT_PERIOD = 3600  # 1 hour
```

### Health Checks

#### Application Health Check

```python
# src/app/api/v1/health.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.db.database import async_get_db
from ...core.utils.cache import redis_client

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@router.get("/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(async_get_db)):
    health_status = {"status": "healthy", "services": {}}
    
    # Check database
    try:
        await db.execute("SELECT 1")
        health_status["services"]["database"] = "healthy"
    except Exception:
        health_status["services"]["database"] = "unhealthy"
        health_status["status"] = "unhealthy"
    
    # Check Redis
    try:
        await redis_client.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception:
        health_status["services"]["redis"] = "unhealthy"
        health_status["status"] = "unhealthy"
    
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status
```

### Deployment Process

#### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build and push Docker image
        env:
          DOCKER_REGISTRY: your-registry.com
        run: |
          docker build -t $DOCKER_REGISTRY/fastapi-app:latest .
          docker push $DOCKER_REGISTRY/fastapi-app:latest
      
      - name: Deploy to production
        run: |
          # Your deployment commands
          ssh production-server "docker compose pull && docker compose up -d"
```

#### Zero-Downtime Deployment

```bash
#!/bin/bash
# deploy.sh - Zero-downtime deployment script

# Pull new images
docker compose pull

# Start new containers
docker compose up -d --no-deps --scale web=2 web

# Wait for health check
sleep 30

# Stop old containers
docker compose up -d --no-deps --scale web=1 web

# Clean up
docker system prune -f
```

### Monitoring and Alerting

#### Basic Monitoring Setup

```python
# Basic metrics collection
import psutil
from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics")
async def get_metrics():
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent
    }
```

### Backup Strategy

#### Database Backup

```bash
#!/bin/bash
# backup-db.sh
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

pg_dump -h localhost -U $POSTGRES_USER $POSTGRES_DB | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 7 days of backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

## Troubleshooting

### Common Production Issues

**High Memory Usage**: Check for memory leaks, optimize database queries, adjust worker counts

**Slow Response Times**: Enable query logging, check database indexes, optimize N+1 queries

**Connection Timeouts**: Adjust proxy timeouts, check database connection pool settings

**SSL Certificate Issues**: Verify certificate paths, check renewal process

### Performance Tuning

- Monitor database query performance
- Implement proper caching strategies
- Use connection pooling
- Optimize Docker image layers
- Configure proper resource limits

This production guide provides a solid foundation for deploying the FastAPI boilerplate to production environments with proper performance, security, and reliability configurations. 