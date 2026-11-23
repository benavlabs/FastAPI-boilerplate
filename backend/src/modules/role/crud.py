from fastcrud import FastCRUD
from pydantic import BaseModel

from .models import Role
from .schemas import RoleCreate, RoleUpdate

crud_roles = FastCRUD[Role, RoleCreate, RoleUpdate, RoleUpdate, BaseModel, BaseModel](Role)
