# Project Structure

Understanding the project structure is essential for navigating the FastAPI Boilerplate effectively. This guide explains the organization of the codebase, the purpose of each directory, and how components interact with each other.

## Overview

The FastAPI Boilerplate follows a clean, modular architecture that separates concerns and promotes maintainability. The structure is designed to scale from simple APIs to complex applications while maintaining code organization and clarity.

## Root Directory Structure

```text
FastAPI-boilerplate/
├── Dockerfile                 # Container configuration
├── docker-compose.yml         # Multi-service orchestration
├── pyproject.toml            # Project configuration and dependencies
├── uv.lock                   # Dependency lock file
├── README.md                 # Project documentation
├── LICENSE.md                # License information
├── tests/                    # Test suite
├── docs/                     # Documentation
└── src/                      # Source code
```

### Configuration Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Defines the container image for the application |
| `docker-compose.yml` | Orchestrates multiple services (API, database, Redis, worker) |
| `pyproject.toml` | Modern Python project configuration with dependencies and metadata |
| `uv.lock` | Locks exact dependency versions for reproducible builds |

## Source Code Structure

The `src/` directory contains all application code:

```text
src/
├── app/                      # Main application package
│   ├── main.py              # Application entry point
│   ├── api/                 # API layer
│   ├── core/                # Core utilities and configurations
│   ├── crud/                # Database operations
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── middleware/          # Custom middleware
│   └── logs/                # Application logs
├── migrations/              # Database migrations
└── scripts/                 # Utility scripts
```

## Core Application (`src/app/`)

### Entry Point
- **`main.py`** - FastAPI application instance and configuration

### API Layer (`api/`)
```text
api/
├── dependencies.py          # Shared dependencies
└── v1/                     # API version 1
    ├── login.py            # Authentication endpoints
    ├── logout.py           # Logout functionality
    ├── users.py            # User management
    ├── posts.py            # Post operations
    ├── tasks.py            # Background task endpoints
    ├── tiers.py            # User tier management
    └── rate_limits.py      # Rate limiting endpoints
```

**Purpose**: Contains all API endpoints organized by functionality and version.

### Core System (`core/`)
```text
core/
├── config.py               # Application settings
├── logger.py               # Logging configuration
├── schemas.py              # Core Pydantic schemas
├── security.py             # Security utilities
├── setup.py                # Application factory
├── db/                     # Database core
├── exceptions/             # Custom exceptions
├── utils/                  # Utility functions
└── worker/                 # Background worker
```

**Purpose**: Houses core functionality, configuration, and shared utilities.

#### Database Core (`core/db/`)
```text
db/
├── database.py             # Database connection and session management
├── models.py               # Base models and mixins
├── crud_token_blacklist.py # Token blacklist operations
└── token_blacklist.py      # Token blacklist model
```

#### Exceptions (`core/exceptions/`)
```text
exceptions/
├── cache_exceptions.py     # Cache-related exceptions
└── http_exceptions.py      # HTTP exceptions
```

#### Utilities (`core/utils/`)
```text
utils/
├── cache.py                # Caching utilities
├── queue.py                # Task queue management
└── rate_limit.py           # Rate limiting utilities
```

#### Worker (`core/worker/`)
```text
worker/
├── settings.py             # Worker configuration
└── functions.py            # Background task definitions
```

### Data Layer

#### Models (`models/`)
```text
models/
├── user.py                 # User model
├── post.py                 # Post model
├── tier.py                 # User tier model
└── rate_limit.py           # Rate limit model
```

**Purpose**: SQLAlchemy ORM models defining database schema.

#### Schemas (`schemas/`)
```text
schemas/
├── user.py                 # User validation schemas
├── post.py                 # Post validation schemas
├── tier.py                 # Tier validation schemas
├── rate_limit.py           # Rate limit schemas
└── job.py                  # Background job schemas
```

**Purpose**: Pydantic schemas for request/response validation and serialization.

#### CRUD Operations (`crud/`)
```text
crud/
├── crud_base.py            # Base CRUD class
├── crud_users.py           # User operations
├── crud_posts.py           # Post operations
├── crud_tier.py            # Tier operations
├── crud_rate_limit.py      # Rate limit operations
└── helper.py               # CRUD helper functions
```

**Purpose**: Database operations using FastCRUD for consistent data access patterns.

### Additional Components

#### Middleware (`middleware/`)
```text
middleware/
└── client_cache_middleware.py  # Client-side caching middleware
```

#### Logs (`logs/`)
```text
logs/
└── app.log                 # Application log file
```

## Database Migrations (`src/migrations/`)

```text
migrations/
├── README                  # Migration instructions
├── env.py                  # Alembic environment configuration
├── script.py.mako          # Migration template
└── versions/               # Individual migration files
```

**Purpose**: Alembic database migrations for schema version control.

## Utility Scripts (`src/scripts/`)

```text
scripts/
├── create_first_superuser.py  # Create initial admin user
└── create_first_tier.py       # Create initial user tier
```

**Purpose**: Initialization and maintenance scripts.

## Testing Structure (`tests/`)

```text
tests/
├── conftest.py             # Pytest configuration and fixtures
├── test_user_unit.py       # User-related unit tests
└── helpers/                # Test utilities
    ├── generators.py       # Test data generators
    └── mocks.py            # Mock objects and functions
```

## Architectural Patterns

### Layered Architecture

The boilerplate implements a clean layered architecture:

1. **API Layer** (`api/`) - Handles HTTP requests and responses
2. **Business Logic** (`crud/`) - Implements business rules and data operations
3. **Data Access** (`models/`) - Defines data structure and database interaction
4. **Core Services** (`core/`) - Provides shared functionality and configuration

### Dependency Injection

FastAPI's dependency injection system is used throughout:

- **Database Sessions** - Injected into endpoints via `async_get_db`
- **Authentication** - User context provided by `get_current_user`
- **Rate Limiting** - Applied via `rate_limiter_dependency`
- **Caching** - Managed through decorators and middleware

### Configuration Management

All configuration is centralized in `core/config.py`:

- **Environment Variables** - Loaded from `.env` file
- **Settings Classes** - Organized by functionality (database, security, etc.)
- **Type Safety** - Using Pydantic for validation

### Error Handling

Centralized exception handling:

- **Custom Exceptions** - Defined in `core/exceptions/`
- **HTTP Status Codes** - Consistent error responses
- **Logging** - Automatic error logging and tracking

## Design Principles

### Single Responsibility

Each module has a clear, single purpose:

- Models define data structure
- Schemas handle validation
- CRUD manages data operations
- API endpoints handle requests

### Separation of Concerns

- Business logic separated from presentation
- Database operations isolated from API logic
- Configuration centralized and environment-aware

### Modularity

- Features can be added/removed independently
- Services can be disabled via configuration
- Clear interfaces between components

### Scalability

- Async/await throughout the application
- Connection pooling for database access
- Caching and background task support
- Horizontal scaling ready

## Navigation Tips

### Finding Code

- **Models** → `src/app/models/`
- **API Endpoints** → `src/app/api/v1/`
- **Database Operations** → `src/app/crud/`
- **Configuration** → `src/app/core/config.py`
- **Business Logic** → Distributed across CRUD and API layers

### Adding New Features

1. **Model** → Define in `models/`
2. **Schema** → Create in `schemas/`
3. **CRUD** → Implement in `crud/`
4. **API** → Add endpoints in `api/v1/`
5. **Migration** → Generate with Alembic

### Understanding Data Flow

```text
Request → API Endpoint → Dependencies → CRUD → Model → Database
Response ← API Response ← Schema ← CRUD ← Query Result ← Database
```

This structure provides a solid foundation for building scalable, maintainable APIs while keeping the codebase organized and easy to navigate. 