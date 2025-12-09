from fastapi import APIRouter, Depends, HTTPException, Path
from ...core.authz.casbin import enforcer
from ...schemas.role import RoleCreate, RoleUpdate, RoleRead, Permission
from ...api.dependencies import get_current_superuser

router = APIRouter(tags=["roles"])

def ensure_role_prefix(name: str) -> str:
    return name if name.startswith("role:") else f"role:{name}"

@router.get("/roles", response_model=list[RoleRead], dependencies=[Depends(get_current_superuser)])
async def get_roles():
    """
    Get all roles and their permissions.
    """
    if not enforcer:
        raise HTTPException(status_code=503, detail="Authorization service not available")

    # Collect all unique roles from policies (p) and groupings (g)
    roles = set()
    
    # From 'p' policies (subjects)
    all_subjects = enforcer.get_all_subjects()
    for sub in all_subjects:
        if sub.startswith("role:"):
            roles.add(sub)
            
    # From 'g' policies (roles)
    # get_filtered_grouping_policy(0) returns all 'g' rules
    # g rules are [user, role]
    grouping_policies = enforcer.get_filtered_grouping_policy(0)
    for rule in grouping_policies:
        if len(rule) > 1 and rule[1].startswith("role:"):
            roles.add(rule[1])
            
    result = []
    for role in roles:
        # Get permissions for this role
        perms = []
        # get_filtered_policy(field_index, field_value) -> returns rules where sub == role
        policy_rules = enforcer.get_filtered_policy(0, role)
        for rule in policy_rules:
            # rule: [sub, obj, act]
            if len(rule) >= 3:
                perms.append(Permission(resource=rule[1], action=rule[2]))
        
        result.append(RoleRead(name=role, permissions=perms))
    
    return result

@router.post("/roles", dependencies=[Depends(get_current_superuser)])
async def create_role(role: RoleCreate):
    """
    Create a new role with permissions.
    """
    if not enforcer:
        raise HTTPException(status_code=503, detail="Authorization service not available")

    role_name = ensure_role_prefix(role.name)
    
    # Add permissions
    for perm in role.permissions:
        await enforcer.add_policy(role_name, perm.resource, perm.action)
        
    return {"message": "Role created successfully"}

@router.put("/roles/{role_name}", dependencies=[Depends(get_current_superuser)])
async def update_role(role_name: str, role_data: RoleUpdate):
    """
    Update a role's permissions (Overwrites existing permissions).
    """
    if not enforcer:
        raise HTTPException(status_code=503, detail="Authorization service not available")

    full_role_name = ensure_role_prefix(role_name)
    
    # 1. Remove all existing permissions for this role
    # field_index 0 is 'sub'
    await enforcer.remove_filtered_policy(0, full_role_name)
    
    # 2. Add new permissions
    for perm in role_data.permissions:
        await enforcer.add_policy(full_role_name, perm.resource, perm.action)
        
    return {"message": "Role updated successfully"}

@router.delete("/roles/{role_name}", dependencies=[Depends(get_current_superuser)])
async def delete_role(role_name: str):
    """
    Delete a role. Fails if the role is assigned to any user.
    """
    if not enforcer:
        raise HTTPException(status_code=503, detail="Authorization service not available")

    full_role_name = ensure_role_prefix(role_name)
    
    # Check if any user has this role
    users = enforcer.get_users_for_role(full_role_name)
    if users:
        raise HTTPException(status_code=400, detail=f"Role is assigned to {len(users)} users. Cannot delete.")
    
    # Delete permissions (p policies)
    await enforcer.remove_filtered_policy(0, full_role_name)
    # Delete groupings (g policies) where role is the group
    # g: [user, role] -> role is at index 1
    await enforcer.remove_filtered_grouping_policy(1, full_role_name)
    
    return {"message": "Role deleted successfully"}
