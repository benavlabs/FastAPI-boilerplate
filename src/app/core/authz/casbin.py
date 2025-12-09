import os
import casbin
import casbin_async_sqlalchemy_adapter
from ..db.database import DATABASE_URL

# Global enforcer instance
enforcer: casbin.AsyncEnforcer | None = None

async def init_enforcer():
    global enforcer
    # Initialize adapter with the async database URL
    adapter = casbin_async_sqlalchemy_adapter.Adapter(DATABASE_URL)
    
    # Ensure table exists (create_table is an async method in this adapter)
    # The adapter documentation suggests it handles table creation, but explicit check is safer if supported
    if hasattr(adapter, 'create_table'):
        await adapter.create_table()
    
    model_path = os.path.join(os.path.dirname(__file__), 'model.conf')
    
    # Use AsyncEnforcer for async adapter compatibility
    enforcer = casbin.AsyncEnforcer(model_path, adapter)
    
    # Load policies from database
    await enforcer.load_policy()
    
    return enforcer
