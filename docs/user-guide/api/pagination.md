# API Pagination

This guide shows you how to add pagination to your API endpoints using the boilerplate's built-in utilities. Pagination helps you handle large datasets efficiently.

## Quick Start

Here's how to add basic pagination to any endpoint:

```python
from fastcrud.paginated import PaginatedListResponse

@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    page: int = 1,
    items_per_page: int = 10,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserRead,
        return_as_model=True,
        return_total_count=True
    )
    
    return paginated_response(
        crud_data=users,
        page=page,
        items_per_page=items_per_page
    )
```

That's it! Your endpoint now returns paginated results with metadata.

## What You Get

The response includes everything frontends need:

```json
{
    "data": [
        {
            "id": 1,
            "name": "John Doe",
            "username": "johndoe",
            "email": "john@example.com"
        }
        // ... more users
    ],
    "total_count": 150,
    "has_more": true,
    "page": 1,
    "items_per_page": 10,
    "total_pages": 15
}
```

## Adding Filters

You can easily add filtering to paginated endpoints:

```python
@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    page: int = 1,
    items_per_page: int = 10,
    # Add filter parameters
    search: str | None = None,
    is_active: bool | None = None,
    tier_id: int | None = None,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Build filters
    filters = {}
    if search:
        filters["name__icontains"] = search  # Search by name
    if is_active is not None:
        filters["is_active"] = is_active
    if tier_id:
        filters["tier_id"] = tier_id
    
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserRead,
        return_as_model=True,
        return_total_count=True,
        **filters
    )
    
    return paginated_response(
        crud_data=users,
        page=page,
        items_per_page=items_per_page
    )
```

Now you can call:

- `/users/?search=john` - Find users with "john" in their name
- `/users/?is_active=true` - Only active users
- `/users/?tier_id=1&page=2` - Users in tier 1, page 2

## Adding Sorting

Add sorting options to your paginated endpoints:

```python
@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    page: int = 1,
    items_per_page: int = 10,
    # Add sorting parameters
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserRead,
        return_as_model=True,
        return_total_count=True,
        sort_columns=sort_by,
        sort_orders=sort_order
    )
    
    return paginated_response(
        crud_data=users,
        page=page,
        items_per_page=items_per_page
    )
```

Usage:

- `/users/?sort_by=name&sort_order=asc` - Sort by name A-Z
- `/users/?sort_by=created_at&sort_order=desc` - Newest first

## Validation

Add validation to prevent issues:

```python
from fastapi import Query

@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    page: Annotated[int, Query(ge=1)] = 1,                    # Must be >= 1
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10, # Between 1-100
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Your pagination logic here
```

## Complete Example

Here's a full-featured paginated endpoint:

```python
@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    # Pagination
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10,
    
    # Filtering
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    tier_id: int | None = None,
    
    # Sorting
    sort_by: str = "created_at",
    sort_order: str = "desc",
    
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    """Get paginated users with filtering and sorting."""
    
    # Build filters
    filters = {"is_deleted": False}  # Always exclude deleted users
    
    if is_active is not None:
        filters["is_active"] = is_active
    if tier_id:
        filters["tier_id"] = tier_id
    
    # Handle search
    search_criteria = []
    if search:
        from sqlalchemy import or_, func
        search_criteria = [
            or_(
                func.lower(User.name).contains(search.lower()),
                func.lower(User.username).contains(search.lower()),
                func.lower(User.email).contains(search.lower())
            )
        ]
    
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserRead,
        return_as_model=True,
        return_total_count=True,
        sort_columns=sort_by,
        sort_orders=sort_order,
        **filters,
        **{"filter_criteria": search_criteria} if search_criteria else {}
    )
    
    return paginated_response(
        crud_data=users,
        page=page,
        items_per_page=items_per_page
    )
```

This endpoint supports:

- `/users/` - First 10 users
- `/users/?page=2&items_per_page=20` - Page 2, 20 items
- `/users/?search=john&is_active=true` - Active users named john
- `/users/?sort_by=name&sort_order=asc` - Sorted by name

## Simple List (No Pagination)

Sometimes you just want a simple list without pagination:

```python
@router.get("/all", response_model=list[UserRead])
async def get_all_users(
    limit: int = 100,  # Prevent too many results
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    users = await crud_users.get_multi(
        db=db,
        limit=limit,
        schema_to_select=UserRead,
        return_as_model=True
    )
    return users["data"]
```

## Performance Tips

1. **Always set a maximum page size**:
```python
items_per_page: Annotated[int, Query(ge=1, le=100)] = 10  # Max 100 items
```

2. **Use `schema_to_select` to only fetch needed fields**:
```python
users = await crud_users.get_multi(
    schema_to_select=UserRead,  # Only fetch UserRead fields
    return_as_model=True
)
```

3. **Add database indexes** for columns you sort by:
```sql
-- In your migration
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_name ON users(name);
```

## Common Patterns

### Admin List with All Users
```python
@router.get("/admin", dependencies=[Depends(get_current_superuser)])
async def get_all_users_admin(
    include_deleted: bool = False,
    page: int = 1,
    items_per_page: int = 50,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    filters = {}
    if not include_deleted:
        filters["is_deleted"] = False
    
    users = await crud_users.get_multi(db=db, **filters)
    return paginated_response(users, page, items_per_page)
```

### User's Own Items
```python
@router.get("/my-posts", response_model=PaginatedListResponse[PostRead])
async def get_my_posts(
    page: int = 1,
    items_per_page: int = 10,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    posts = await crud_posts.get_multi(
        db=db,
        author_id=current_user["id"],  # Only user's own posts
        offset=(page - 1) * items_per_page,
        limit=items_per_page
    )
    return paginated_response(posts, page, items_per_page)
```

## What's Next

Now that you understand pagination:

- **[Database CRUD](../database/crud.md)** - Learn more about the CRUD operations
- **[Database Schemas](../database/schemas.md)** - Create schemas for your data
- **[Authentication](../authentication/index.md)** - Add user authentication to your endpoints

The boilerplate makes pagination simple - just use these patterns! 