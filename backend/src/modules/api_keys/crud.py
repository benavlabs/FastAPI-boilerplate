from fastcrud import FastCRUD
from pydantic import BaseModel

from .models import APIKey, KeyUsage
from .schemas import APIKeyCreateInternal, APIKeyUpdate, KeyUsageCreate

crud_api_keys = FastCRUD[APIKey, APIKeyCreateInternal, APIKeyUpdate, APIKeyUpdate, BaseModel, BaseModel](APIKey)
crud_key_usage = FastCRUD[KeyUsage, KeyUsageCreate, BaseModel, BaseModel, BaseModel, BaseModel](KeyUsage)
