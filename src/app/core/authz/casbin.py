import os

import casbin
import casbin_async_sqlalchemy_adapter

from ..db.database import DATABASE_URL

adapter = casbin_async_sqlalchemy_adapter.Adapter(DATABASE_URL)
model_path = os.path.join(os.path.dirname(__file__), "model.conf")
enforcer: casbin.AsyncEnforcer = casbin.AsyncEnforcer(model_path, adapter)


async def _seed_default_policies() -> None:
    await enforcer.add_grouping_policy("anonymous", "role:anonymous")
    await enforcer.add_policy("role:anonymous", "/api/v1/health", "GET")
    await enforcer.add_policy("role:anonymous", "/api/v1/ready", "GET")
    await enforcer.add_policy("role:anonymous", "/api/v1/login", "POST")
    await enforcer.add_policy("role:anonymous", "/api/v1/refresh", "POST")
    await enforcer.add_policy("role:anonymous", "/docs", "GET")
    await enforcer.add_policy("role:anonymous", "/redoc", "GET")
    await enforcer.add_policy("role:anonymous", "/openapi.json", "GET")
    await enforcer.add_policy("role:superuser", "/*", "GET|POST|PUT|PATCH|DELETE")


async def initialize_enforcer() -> casbin.AsyncEnforcer:
    if hasattr(adapter, "create_table"):
        await adapter.create_table()
    await enforcer.load_policy()
    enforcer.enable_auto_save(True)
    await _seed_default_policies()
    return enforcer
