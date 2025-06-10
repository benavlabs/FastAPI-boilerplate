# Cache Strategies

Effective cache strategies balance performance gains with data consistency. This section covers invalidation patterns, cache warming, and optimization techniques for building robust caching systems.

## Cache Invalidation Strategies

Cache invalidation is one of the hardest problems in computer science. The boilerplate provides several strategies to handle different scenarios while maintaining data consistency.

### Understanding Cache Invalidation

**Cache invalidation** ensures that cached data doesn't become stale when the underlying data changes. Poor invalidation leads to users seeing outdated information, while over-aggressive invalidation negates caching benefits.

### Basic Invalidation Patterns

#### Time-Based Expiration (TTL)

The simplest strategy relies on cache expiration times:

```python
# Set different TTL based on data characteristics
@cache(key_prefix="user_profile", expiration=3600)  # 1 hour for profiles
@cache(key_prefix="post_content", expiration=1800)  # 30 min for posts
@cache(key_prefix="live_stats", expiration=60)      # 1 min for live data
```

**Pros:**

- Simple to implement and understand
- Guarantees cache freshness within TTL period
- Works well for data with predictable change patterns

**Cons:**

- May serve stale data until TTL expires
- Difficult to optimize TTL for all scenarios
- Cache miss storms when many keys expire simultaneously

#### Write-Through Invalidation

Automatically invalidate cache when data is modified:

```python
@router.put("/posts/{post_id}")
@cache(
    key_prefix="post_cache",
    resource_id_name="post_id",
    to_invalidate_extra={
        "user_posts": "{user_id}",           # User's post list
        "category_posts": "{category_id}",   # Category post list
        "recent_posts": "global"             # Global recent posts
    }
)
async def update_post(
    request: Request,
    post_id: int,
    post_data: PostUpdate,
    user_id: int,
    category_id: int
):
    # Update triggers automatic cache invalidation
    updated_post = await crud_posts.update(db=db, id=post_id, object=post_data)
    return updated_post
```

**Pros:**

- Immediate consistency when data changes
- No stale data served to users
- Precise control over what gets invalidated

**Cons:**

- More complex implementation
- Can impact write performance
- Risk of over-invalidation

### Advanced Invalidation Patterns

#### Pattern-Based Invalidation

Use Redis pattern matching for bulk invalidation:

```python
@router.put("/users/{user_id}/profile")
@cache(
    key_prefix="user_profile",
    resource_id_name="user_id",
    pattern_to_invalidate_extra=[
        "user_{user_id}_*",          # All user-related caches
        "*_user_{user_id}_*",        # Caches containing this user
        "leaderboard_*",             # Leaderboards might change
        "search_users_*"             # User search results
    ]
)
async def update_user_profile(request: Request, user_id: int, profile_data: ProfileUpdate):
    await crud_users.update(db=db, id=user_id, object=profile_data)
    return {"message": "Profile updated"}
```

**Pattern Examples:**
```python
# User-specific patterns
"user_{user_id}_posts_*"        # All paginated post lists for user
"user_{user_id}_*_cache"        # All cached data for user
"*_following_{user_id}"          # All caches tracking this user's followers

# Content patterns  
"posts_category_{category_id}_*" # All posts in category
"comments_post_{post_id}_*"      # All comments for post
"search_*_{query}"               # All search results for query

# Time-based patterns
"daily_stats_*"                  # All daily statistics
"hourly_*"                       # All hourly data
"temp_*"                         # Temporary cache entries
```

## Cache Warming Strategies

Cache warming proactively loads data into cache to avoid cache misses during peak usage.

### Application Startup Warming

```python
# core/startup.py
async def warm_critical_caches():
    """Warm up critical caches during application startup."""
    
    logger.info("Starting cache warming...")
    
    # Warm up reference data
    await warm_reference_data()
    
    # Warm up popular content
    await warm_popular_content()
    
    # Warm up user session data for active users
    await warm_active_user_data()
    
    logger.info("Cache warming completed")

async def warm_reference_data():
    """Warm up reference data that rarely changes."""
    
    # Countries, currencies, timezones, etc.
    reference_data = await crud_reference.get_all_countries()
    for country in reference_data:
        cache_key = f"country:{country['code']}"
        await cache.client.set(cache_key, json.dumps(country), ex=86400)  # 24 hours
    
    # Categories
    categories = await crud_categories.get_all()
    await cache.client.set("all_categories", json.dumps(categories), ex=3600)

async def warm_popular_content():
    """Warm up frequently accessed content."""
    
    # Most viewed posts
    popular_posts = await crud_posts.get_popular(limit=100)
    for post in popular_posts:
        cache_key = f"post_cache:{post['id']}"
        await cache.client.set(cache_key, json.dumps(post), ex=1800)
    
    # Trending topics
    trending = await crud_posts.get_trending_topics(limit=50)
    await cache.client.set("trending_topics", json.dumps(trending), ex=600)

async def warm_active_user_data():
    """Warm up data for recently active users."""
    
    # Get users active in last 24 hours
    active_users = await crud_users.get_recently_active(hours=24)
    
    for user in active_users:
        # Warm user profile
        profile_key = f"user_profile:{user['id']}"
        await cache.client.set(profile_key, json.dumps(user), ex=3600)
        
        # Warm user's recent posts
        user_posts = await crud_posts.get_user_posts(user['id'], limit=10)
        posts_key = f"user_{user['id']}_posts:page_1"
        await cache.client.set(posts_key, json.dumps(user_posts), ex=1800)

# Add to startup events
@app.on_event("startup")
async def startup_event():
    await create_redis_cache_pool()
    await warm_critical_caches()
```

These cache strategies provide a comprehensive approach to building performant, consistent caching systems that scale with your application's needs while maintaining data integrity. 