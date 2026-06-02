# Fastro · The Benav Labs FastAPI Boilerplate

<p align="center">
  <img src="assets/fastro-cover-light.png#only-light" alt="Fastro - open-source FastAPI boilerplate" width="100%">
  <img src="assets/fastro-cover-dark.png#only-dark" alt="Fastro - open-source FastAPI boilerplate" width="100%">
</p>

<p align="center">
  <i>A production-ready FastAPI boilerplate to speed up your development.</i>
</p>

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
- **[Taskiq](https://taskiq-python.github.io/)** - Async-first task queue with Redis/RabbitMQ brokers
- **[Docker](https://docs.docker.com/compose/)** - Containerization for easy deployment

## Key Features

### Performance & Scalability
- Fully async architecture
- Pydantic V2 for ultra-fast data validation
- SQLAlchemy 2.0 with efficient query patterns
- Built-in caching with Redis or Memcached

### Security & Authentication
- Server-side session authentication with secure HTTP-only cookies
- OAuth 2.0 sign-in (Google, with GitHub provider scaffolded) using PKCE
- API keys with per-key permissions and usage tracking
- CSRF protection and login rate limiting
- Role-based access control with user tiers
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
- Database connection pooling
- Async task processing with Taskiq workers

## Quick Start

Get up and running in less than 5 minutes. Pick whichever fits your workflow:

=== "Local with uv"

    ```bash
    git clone https://github.com/benavlabs/fastapi-boilerplate
    cd fastapi-boilerplate/backend
    uv sync --extra dev
    cp .env.example .env  # then edit values as needed
    uv run fastapi dev src/interfaces/main.py
    ```

=== "Docker Compose"

    ```bash
    git clone https://github.com/benavlabs/fastapi-boilerplate
    cd fastapi-boilerplate/backend
    docker compose up
    ```

Your API will be available at `http://localhost:8000/docs`

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

## Building a complete SaaS? Meet FastroAI

Fastro is the free **foundation**. **[FastroAI](https://fastro.ai)** builds on the same base for shipping a full SaaS - Stripe billing (subscriptions, credits, discounts), entitlements, transactional email, a frontend, and AI agents - all wired together, so you don't build them from scratch.

<p align="center">
  <a href="https://fastro.ai">
    <img src="assets/fastroai-card-light.png#only-light" alt="FastroAI - the complete SaaS template" width="100%">
    <img src="assets/fastroai-card-dark.png#only-dark" alt="FastroAI - the complete SaaS template" width="100%">
  </a>
</p>

## Community & Support

- **[Discord Community](community.md)** - Join our Discord server to connect with other developers
- **[GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues)** - Bug reports and feature requests

<hr>
<a href="https://benav.io">
  <img src="assets/benav-labs-banner-light.png#only-light" alt="Benav Labs - benav.io"/>
  <img src="assets/benav-labs-banner-dark.png#only-dark" alt="Benav Labs - benav.io"/>
</a>