# Background Tasks

The boilerplate includes a robust background task system built on ARQ (Async Redis Queue) for handling long-running operations asynchronously. This enables your API to remain responsive while processing intensive tasks in the background.

## Overview

Background tasks are essential for operations that:

- **Take longer than 2 seconds** to complete
- **Don't block user interactions** in your frontend
- **Can be processed asynchronously** without immediate user feedback
- **Require intensive computation** or external API calls

## Quick Example

```python
# Define a background task
async def send_welcome_email(ctx: Worker, user_id: int, email: str) -> str:
    # Send email logic here
    await send_email_service(email, "Welcome!")
    return f"Welcome email sent to {email}"

# Enqueue the task from an API endpoint
@router.post("/users/", response_model=UserRead)
async def create_user(user_data: UserCreate):
    # Create user in database
    user = await crud_users.create(db=db, object=user_data)
    
    # Queue welcome email in background
    await queue.pool.enqueue_job("send_welcome_email", user["id"], user["email"])
    
    return user
```

## Architecture

### ARQ Worker System
- **Redis-Based**: Uses Redis as the message broker for job queues
- **Async Processing**: Fully asynchronous task execution  
- **Worker Pool**: Multiple workers can process tasks concurrently
- **Job Persistence**: Tasks survive application restarts

### Task Lifecycle
1. **Enqueue**: Tasks are added to Redis queue from API endpoints
2. **Processing**: ARQ workers pick up and execute tasks
3. **Results**: Task results are stored and can be retrieved
4. **Monitoring**: Track task status and execution history

## Key Features

**Scalable Processing**
- Multiple worker instances for high throughput
- Automatic load balancing across workers
- Configurable concurrency per worker

**Reliable Execution**
- Task retry mechanisms for failed jobs
- Dead letter queues for problematic tasks
- Graceful shutdown and task cleanup

**Database Integration**
- Shared database sessions with main application
- CRUD operations available in background tasks
- Transaction management and error handling

## Common Use Cases

- **Email Processing**: Welcome emails, notifications, newsletters
- **File Operations**: Image processing, PDF generation, file uploads
- **External APIs**: Third-party integrations, webhooks, data sync
- **Data Processing**: Report generation, analytics, batch operations
- **ML/AI Tasks**: Model inference, data analysis, predictions

## Getting Started

The boilerplate provides everything needed to start using background tasks immediately. Simply define your task functions, register them in the worker settings, and enqueue them from your API endpoints.

## Configuration

Basic Redis queue configuration:

```bash
# Redis Queue Settings  
REDIS_QUEUE_HOST=localhost
REDIS_QUEUE_PORT=6379
```

The system automatically handles Redis connection pooling and worker lifecycle management.

## Next Steps

Check the [ARQ documentation](https://arq-docs.helpmanual.io/) for advanced usage patterns and refer to the boilerplate's example implementation in `src/app/core/worker/` and `src/app/api/v1/tasks.py`. 