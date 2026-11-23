from fastcrud import FastCRUD
from pydantic import BaseModel

from .models import User
from .schemas import UserAnonymize, UserCreateInternal, UserDelete, UserUpdate, UserUpdateInternal

crud_users = FastCRUD[User, UserCreateInternal, UserUpdate | UserAnonymize, UserUpdateInternal, UserDelete, BaseModel](User)
