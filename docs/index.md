# Benav Labs FastAPI Boilerplate

<p align="center">
  <img src="assets/FastAPI-boilerplate.png" alt="Purple Rocket with FastAPI Logo as its window." width="35%" height="auto">
</p>

<p align="center">
  <i>A production-ready FastAPI boilerplate to speed up your development.</i>
</p>

!!! warning "Documentation Status"
    This is our first version of the documentation. While functional, we acknowledge it's rough around the edges - there's a huge amount to document and we needed to start somewhere! We built this foundation (with a lot of AI assistance) so we can improve upon it. 
    
    Better documentation, examples, and guides are actively being developed. Contributions and feedback are greatly appreciated!

<p align="center">
  <a href="https://fastapi.tiangolo.com">
      <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
  </a>
  <a href="https://docs.pydantic.dev/2.4/">
      <img src="https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=fff&style=for-the-badge" alt="Pydantic">
  </a>
  <a href="https://www.postgresql.org">
      <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  </a>
  <a href="https://redis.io">
      <img src="https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=fff&style=for-the-badge" alt="Redis">
  </a>
  <a href="https://docs.docker.com/compose/">
      <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=fff&style=for-the-badge" alt="Docker">
  </a>
</p>

## What is FastAPI Boilerplate?

FastAPI Boilerplate is a comprehensive, production-ready template that provides everything you need to build scalable, async APIs using modern Python technologies. It combines the power of FastAPI with industry best practices to give you a solid foundation for your next project.

## Core Technologies

This boilerplate leverages cutting-edge Python technologies:

- **[FastAPI](https://fastapi.tiangolo.com)** - Modern, fast web framework for building APIs with Python 3.7+
- **[Pydantic V2](https://docs.pydantic.dev/2.4/)** - Data validation library rewritten in Rust (5x-50x faster)
- **[SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)** - Python SQL toolkit and Object Relational Mapper
- **[PostgreSQL](https://www.postgresql.org)** - Advanced open source relational database
- **[Redis](https://redis.io)** - In-memory data store for caching and message brokering
- **[ARQ](https://arq-docs.helpmanual.io)** - Job queues and RPC with asyncio and Redis
- **[Docker](https://docs.docker.com/compose/)** - Containerization for easy deployment
- **[NGINX](https://nginx.org/en/)** - High-performance web server for reverse proxy and load balancing

## Key Features

### Performance & Scalability
- Fully async architecture
- Pydantic V2 for ultra-fast data validation
- SQLAlchemy 2.0 with efficient query patterns
- Built-in caching with Redis
- Horizontal scaling with NGINX load balancing

### Security & Authentication
- JWT-based authentication with refresh tokens
- Cookie-based secure token storage
- Role-based access control with user tiers
- Rate limiting to prevent abuse
- Production-ready security configurations

### Developer Experience
- Comprehensive CRUD operations with [FastCRUD](https://github.com/igorbenav/fastcrud)
- Automatic API documentation
- Database migrations with Alembic
- Background task processing
- Extensive test coverage
- Docker Compose for easy development

### Production Ready
- Environment-based configuration
- Structured logging
- Health checks and monitoring
- NGINX reverse proxy setup
- Gunicorn with Uvicorn workers
- Database connection pooling

## Quick Start

Get up and running in less than 5 minutes:

```bash
# Clone the repository
git clone https://github.com/benavlabs/fastapi-boilerplate
cd fastapi-boilerplate

# Start with Docker Compose
docker compose up
```

That's it! Your API will be available at `http://localhost:8000/docs`

**[Continue with the Getting Started Guide →](getting-started/index.md)**

## Documentation Structure

### For New Users
- **[Getting Started](getting-started/index.md)** - Quick setup and first steps
- **[User Guide](user-guide/index.md)** - Comprehensive feature documentation

### For Developers
- **[Development](user-guide/development.md)** - Extending and customizing the boilerplate
- **[Testing](user-guide/testing.md)** - Testing strategies and best practices
- **[Production](user-guide/production.md)** - Production deployment guides

## Perfect For

- **REST APIs** - Build robust, scalable REST APIs
- **Microservices** - Create microservice architectures
- **SaaS Applications** - Multi-tenant applications with user tiers
- **Data APIs** - APIs for data processing and analytics

## Community & Support

- **[Discord Community](community.md)** - Join our Discord server to connect with other developers
- **[GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues)** - Bug reports and feature requests

<hr>
<a href="https://benav.io">
  <img src="https://github.com/benavlabs/fastcrud/raw/main/docs/assets/benav_labs_banner.png" alt="Powered by Benav Labs - benav.io"/>
</a>