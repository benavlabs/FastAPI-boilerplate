# Getting Started

Welcome to the FastAPI Boilerplate! This guide will have you up and running with a production-ready API in just a few minutes.

## Quick Start (5 minutes)

The fastest way to get started is using Docker Compose. This will set up everything you need including PostgreSQL, Redis, and the API server.

### Prerequisites

Make sure you have installed:

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (1.29+)

### 1. Get the Template

Start by using this template for your new project:

1. Click **"Use this template"** on the [GitHub repository](https://github.com/benavlabs/fastapi-boilerplate)
2. Create a new repository with your project name
3. Clone your new repository:

```bash
git clone https://github.com/yourusername/your-project-name
cd your-project-name
```

### 2. Environment Setup

Create your environment configuration:

```bash
# Create the environment file
touch src/.env
```

Add the following basic configuration to `src/.env`:

```env
# Application
APP_NAME="My FastAPI App"
APP_DESCRIPTION="My awesome API"
APP_VERSION="0.1.0"

# Database
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="changethis"
POSTGRES_SERVER="db"
POSTGRES_PORT=5432
POSTGRES_DB="myapp"

# Security
SECRET_KEY="your-secret-key-here"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Redis
REDIS_CACHE_HOST="redis"
REDIS_CACHE_PORT=6379
REDIS_QUEUE_HOST="redis"
REDIS_QUEUE_PORT=6379

# Admin User
ADMIN_NAME="Admin"
ADMIN_EMAIL="admin@example.com"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="changethis"

# Environment
ENVIRONMENT="local"
```

!!! warning "Security Note"
    Generate a secure secret key using: `openssl rand -hex 32`

### 3. Start the Application

Launch all services with a single command:

```bash
docker compose up
```

This will start:
- **FastAPI server** on port 8000
- **PostgreSQL database** 
- **Redis** for caching and job queues
- **Worker** for background tasks

### 4. Verify Installation

Once the containers are running, you should see output like:

```
fastapi-boilerplate-web-1     | INFO:     Application startup complete.
fastapi-boilerplate-db-1      | database system is ready to accept connections
fastapi-boilerplate-worker-1  | redis_version=7.x.x mem_usage=1MB clients_connected=1
```

Visit these URLs to confirm everything is working:

- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Docs**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## You're Ready!

Congratulations! You now have a fully functional FastAPI application with:

- REST API with automatic documentation
- PostgreSQL database with migrations
- Redis caching and job queues
- JWT authentication system
- Background task processing
- Rate limiting
- Admin user created

## Test Your API

Try these quick tests to see your API in action:

### 1. Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### 2. Create a User
```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "username": "johndoe",
    "email": "john@example.com",
    "password": "securepassword"
  }'
```

### 3. Login
```bash
curl -X POST "http://localhost:8000/api/v1/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=johndoe&password=securepassword"
```

## Next Steps

Now that you have the basics running, explore these guides to learn more:

### Essential Reading
- **[Configuration Guide](configuration.md)** - Understand all configuration options
- **[Project Structure](../user-guide/project-structure.md)** - Learn how the code is organized
- **[Authentication](../user-guide/authentication/index.md)** - Set up user management

### Popular Features
- **[Database Operations](../user-guide/database/index.md)** - Working with models and CRUD
- **[Caching](../user-guide/caching/index.md)** - Speed up your API with Redis caching
- **[Background Tasks](../user-guide/background-tasks/index.md)** - Process jobs asynchronously
- **[Rate Limiting](../user-guide/rate-limiting/index.md)** - Protect your API from abuse

### Development & Deployment
- **[Development Guide](../user-guide/development.md)** - Extend and customize the boilerplate
- **[Testing](../user-guide/testing.md)** - Write tests for your API
- **[Production Deployment](../user-guide/production.md)** - Deploy to production

## Alternative Setup Methods

Not using Docker? No problem!

- **[Manual Installation](installation.md)** - Install dependencies manually

## Need Help?

- Join our **[Discord Community](../community.md)** - Get help from other developers
- Report issues on **[GitHub](https://github.com/benavlabs/fastapi-boilerplate/issues)**

---

**Ready to dive deeper?** Continue with the [detailed installation guide](installation.md) or explore the [user guide](../user-guide/index.md). 