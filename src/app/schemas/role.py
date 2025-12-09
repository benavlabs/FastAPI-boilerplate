from pydantic import BaseModel


class Permission(BaseModel):
    resource: str
    action: str

class RoleBase(BaseModel):
    name: str

class RoleCreate(RoleBase):
    permissions: list[Permission] = []

class RoleUpdate(BaseModel):
    permissions: list[Permission] = []

class RoleRead(RoleBase):
    permissions: list[Permission] = []
