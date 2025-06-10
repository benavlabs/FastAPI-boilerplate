# Database Migrations

This guide covers database migrations using Alembic, the migration tool for SQLAlchemy. Learn how to manage database schema changes safely and efficiently in development and production.

## Overview

The FastAPI Boilerplate uses [Alembic](https://alembic.sqlalchemy.org/) for database migrations. Alembic provides:

- **Version-controlled schema changes** - Track every database modification
- **Automatic migration generation** - Generate migrations from model changes  
- **Reversible migrations** - Upgrade and downgrade database versions
- **Environment-specific configurations** - Different settings for dev/staging/production
- **Safe schema evolution** - Apply changes incrementally

## Simple Setup: Automatic Table Creation

For simple projects or development, the boilerplate includes `create_tables_on_start` parameter that automatically creates all tables on application startup:

```python
# This is enabled by default in create_application()
app = create_application(
    router=router, 
    settings=settings, 
    create_tables_on_start=True  # Default: True
)
```

**When to use:**

- ✅ **Development** - Quick setup without migration management
- ✅ **Simple projects** - When you don't need migration history  
- ✅ **Prototyping** - Fast iteration without migration complexity
- ✅ **Testing** - Clean database state for each test run

**When NOT to use:**

- ❌ **Production** - No migration history or rollback capability
- ❌ **Team development** - Can't track schema changes between developers
- ❌ **Data migrations** - Only handles schema, not data transformations
- ❌ **Complex deployments** - No control over when/how schema changes apply

```python
# Disable for production environments
app = create_application(
    router=router, 
    settings=settings, 
    create_tables_on_start=False  # Use migrations instead
)
```

For production deployments and team development, use proper Alembic migrations as described below.

## Configuration

### Alembic Setup

Alembic is configured in `src/alembic.ini`:

```ini
[alembic]
# Path to migration files
script_location = migrations

# Database URL with environment variable substitution
sqlalchemy.url = postgresql://%(POSTGRES_USER)s:%(POSTGRES_PASSWORD)s@%(POSTGRES_SERVER)s:%(POSTGRES_PORT)s/%(POSTGRES_DB)s

# Other configurations
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
timezone = UTC
```

### Environment Configuration

Migration environment is configured in `src/migrations/env.py`:

```python
# src/migrations/env.py
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.db.database import Base
from app.core.config import settings

# Import all models to ensure they're registered
from app.models import *  # This imports all models

config = context.config

# Override database URL from environment
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata
```

## Migration Workflow

### 1. Creating Migrations

Generate migrations automatically when you change models:

```bash
# Navigate to src directory
cd src

# Generate migration from model changes
uv run alembic revision --autogenerate -m "Add user profile fields"
```

**What happens:**
- Alembic compares current models with database schema
- Generates a new migration file in `src/migrations/versions/`
- Migration includes upgrade and downgrade functions

### 2. Review Generated Migration

Always review auto-generated migrations before applying:

```python
# Example migration file: src/migrations/versions/20241215_1430_add_user_profile_fields.py
"""Add user profile fields

Revision ID: abc123def456
Revises: previous_revision_id
Create Date: 2024-12-15 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123def456'
down_revision = 'previous_revision_id'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add new columns
    op.add_column('user', sa.Column('bio', sa.String(500), nullable=True))
    op.add_column('user', sa.Column('website', sa.String(255), nullable=True))
    
    # Create index
    op.create_index('ix_user_website', 'user', ['website'])

def downgrade() -> None:
    # Remove changes (reverse order)
    op.drop_index('ix_user_website', 'user')
    op.drop_column('user', 'website')
    op.drop_column('user', 'bio')
```

### 3. Apply Migration

Apply migrations to update database schema:

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Apply specific number of migrations
uv run alembic upgrade +2

# Apply to specific revision
uv run alembic upgrade abc123def456
```

### 4. Verify Migration

Check migration status and current version:

```bash
# Show current database version
uv run alembic current

# Show migration history
uv run alembic history

# Show pending migrations
uv run alembic show head
```

## Common Migration Scenarios

### Adding New Model

1. **Create the model** in `src/app/models/`:

```python
# src/app/models/category.py
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.db.database import Base

class Category(Base):
    __tablename__ = "category"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

2. **Import in __init__.py**:

```python
# src/app/models/__init__.py
from .user import User
from .post import Post
from .tier import Tier
from .rate_limit import RateLimit
from .category import Category  # Add new import
```

3. **Generate migration**:

```bash
uv run alembic revision --autogenerate -m "Add category model"
```

### Adding Foreign Key

1. **Update model with foreign key**:

```python
# Add to Post model
category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("category.id"), nullable=True)
```

2. **Generate migration**:

```bash
uv run alembic revision --autogenerate -m "Add category_id to posts"
```

3. **Review and apply**:

```python
# Generated migration will include:
def upgrade() -> None:
    op.add_column('post', sa.Column('category_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_post_category_id', 'post', 'category', ['category_id'], ['id'])
    op.create_index('ix_post_category_id', 'post', ['category_id'])
```

### Data Migrations

Sometimes you need to migrate data, not just schema:

```python
# Example: Populate default category for existing posts
def upgrade() -> None:
    # Add the column
    op.add_column('post', sa.Column('category_id', sa.Integer(), nullable=True))
    
    # Data migration
    connection = op.get_bind()
    
    # Create default category
    connection.execute(
        "INSERT INTO category (name, slug, description) VALUES ('General', 'general', 'Default category')"
    )
    
    # Get default category ID
    result = connection.execute("SELECT id FROM category WHERE slug = 'general'")
    default_category_id = result.fetchone()[0]
    
    # Update existing posts
    connection.execute(
        f"UPDATE post SET category_id = {default_category_id} WHERE category_id IS NULL"
    )
    
    # Make column non-nullable after data migration
    op.alter_column('post', 'category_id', nullable=False)
```

### Renaming Columns

```python
def upgrade() -> None:
    # Rename column
    op.alter_column('user', 'full_name', new_column_name='name')

def downgrade() -> None:
    # Reverse the rename
    op.alter_column('user', 'name', new_column_name='full_name')
```

### Dropping Tables

```python
def upgrade() -> None:
    # Drop table (be careful!)
    op.drop_table('old_table')

def downgrade() -> None:
    # Recreate table structure
    op.create_table('old_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
```

## Production Migration Strategy

### 1. Development Workflow

```bash
# 1. Make model changes
# 2. Generate migration
uv run alembic revision --autogenerate -m "Descriptive message"

# 3. Review migration file
# 4. Test migration
uv run alembic upgrade head

# 5. Test downgrade (optional)
uv run alembic downgrade -1
uv run alembic upgrade head
```

### 2. Staging Deployment

```bash
# 1. Deploy code with migrations
# 2. Backup database
pg_dump -h staging-db -U user dbname > backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Apply migrations
uv run alembic upgrade head

# 4. Verify application works
# 5. Run tests
```

### 3. Production Deployment

```bash
# 1. Schedule maintenance window
# 2. Create database backup
pg_dump -h prod-db -U user dbname > prod_backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Apply migrations (with monitoring)
uv run alembic upgrade head

# 4. Verify health checks pass
# 5. Monitor application metrics
```

## Docker Considerations

### Development with Docker Compose

For local development, migrations run automatically:

```yaml
# docker-compose.yml
services:
  web:
    # ... other config
    depends_on:
      - db
    command: |
      sh -c "
        uv run alembic upgrade head &&
        uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
      "
```

### Production Docker

In production, run migrations separately:

```dockerfile
# Dockerfile migration stage
FROM python:3.11-slim as migration
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ /app/
WORKDIR /app
CMD ["alembic", "upgrade", "head"]
```

```yaml
# docker-compose.prod.yml
services:
  migrate:
    build:
      context: .
      target: migration
    env_file:
      - .env
    depends_on:
      - db
    command: alembic upgrade head
    
  web:
    # ... web service config
    depends_on:
      - migrate
```

## Migration Best Practices

### 1. Always Review Generated Migrations

```python
# Check for issues like:
# - Missing imports
# - Incorrect nullable settings
# - Missing indexes
# - Data loss operations
```

### 2. Use Descriptive Messages

```bash
# Good
uv run alembic revision --autogenerate -m "Add user email verification fields"

# Bad
uv run alembic revision --autogenerate -m "Update user model"
```

### 3. Handle Nullable Columns Carefully

```python
# When adding non-nullable columns to existing tables:
def upgrade() -> None:
    # 1. Add as nullable first
    op.add_column('user', sa.Column('phone', sa.String(20), nullable=True))
    
    # 2. Populate with default data
    op.execute("UPDATE user SET phone = '' WHERE phone IS NULL")
    
    # 3. Make non-nullable
    op.alter_column('user', 'phone', nullable=False)
```

### 4. Test Rollbacks

```bash
# Test that your downgrade works
uv run alembic downgrade -1
uv run alembic upgrade head
```

### 5. Use Transactions for Complex Migrations

```python
def upgrade() -> None:
    # Complex migration with transaction
    connection = op.get_bind()
    trans = connection.begin()
    try:
        # Multiple operations
        op.create_table(...)
        op.add_column(...)
        connection.execute("UPDATE ...")
        trans.commit()
    except:
        trans.rollback()
        raise
```

## Next Steps

- **[CRUD Operations](crud.md)** - Working with migrated database schema
- **[API Development](../api/index.md)** - Building endpoints for your models
- **[Testing](../testing.md)** - Testing database migrations 