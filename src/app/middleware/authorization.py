from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from casbin import util
from ..core.authz.casbin import enforcer
from .authentication import AuthenticatedUser

class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS for CORS preflight checks
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip if enforcer not initialized (e.g. during tests or startup)
        if not enforcer:
             return await call_next(request)
        
        user = request.user
        
        # 1. Superuser Check: Superusers bypass all permission checks
        if user.is_authenticated and isinstance(user, AuthenticatedUser) and user.is_superuser:
             return await call_next(request)
             
        # 2. Casbin Check: Check if there is an explicit allow rule
        # Use user ID for authenticated users, "anonymous" for guests
        sub = str(user.id) if user.is_authenticated and isinstance(user, AuthenticatedUser) else "anonymous"
        obj = request.url.path
        act = request.method
        
        # Enforce permission
        # AsyncEnforcer.enforce is async
        allowed = await enforcer.enforce(sub, obj, act)
        
        if allowed:
             return await call_next(request)
             
        # 3. Default Logic: "Implicit Allow for Authenticated, Implicit Deny for Anonymous"
        # If the resource is NOT explicitly protected (mentioned in any policy),
        # then authenticated users can access it, but anonymous users cannot.
        
        # Check if the resource is "protected" (appears in any policy)
        is_protected = False
        
        # Get all policies to check if any rule covers this path
        # This iterates over all policies, which is fine for typical policy sizes (< thousands)
        # For very large policy sets, this should be optimized (e.g. caching protected paths)
        all_rules = enforcer.get_all_policy()
        
        for rule in all_rules:
            # rule structure is [sub, obj, act]
            # Check if request path matches the policy object pattern
            if len(rule) > 1 and util.key_match2(obj, rule[1]):
                is_protected = True
                break
                
        if not is_protected:
            # If the resource is not protected by any rule:
            if user.is_authenticated:
                # Authenticated users are allowed by default for unspecified resources
                return await call_next(request)
            else:
                # Anonymous users are denied for unspecified resources (Require Login)
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        
        # If the resource IS protected, and enforce failed -> Forbidden
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
