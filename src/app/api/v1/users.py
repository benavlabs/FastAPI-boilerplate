
@router.post("/user/{user_uuid}/roles", dependencies=[Depends(get_current_superuser)])
async def assign_user_roles(user_uuid: str, roles: list[str] = Body(embed=True)) -> dict[str, str]:
    if not enforcer:
         raise NotFoundException("Authorization service not available")

    # 1. Remove existing roles for this user
    # remove_filtered_grouping_policy(field_index, field_value)
    # field_index 0 is the user (g rule: user, role)
    await enforcer.remove_filtered_grouping_policy(0, user_uuid)
    
    # 2. Add new roles
    for role in roles:
        role_name = role if role.startswith("role:") else f"role:{role}"
        await enforcer.add_grouping_policy(user_uuid, role_name)
        
    return {"message": "Roles assigned successfully"}


@router.get("/user/{user_uuid}/roles", dependencies=[Depends(get_current_superuser)])
async def get_user_roles(user_uuid: str) -> dict[str, list[str]]:
    if not enforcer:
         raise NotFoundException("Authorization service not available")
         
    # get_filtered_grouping_policy(0, user_uuid) returns list of [user, role]
    # This reads from memory, so it is synchronous
    grouping_policies = enforcer.get_filtered_grouping_policy(0, user_uuid)
    roles = [rule[1] for rule in grouping_policies if len(rule) > 1]
    
    return {"roles": roles}
