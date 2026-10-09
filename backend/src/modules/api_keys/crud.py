from fastcrud import FastCRUD

from .models import APIKey, KeyUsage

crud_api_keys: FastCRUD = FastCRUD(APIKey)
crud_key_usage: FastCRUD = FastCRUD(KeyUsage)
