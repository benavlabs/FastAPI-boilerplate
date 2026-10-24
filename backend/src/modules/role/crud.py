from fastcrud import FastCRUD

from .models import Role

crud_roles: FastCRUD = FastCRUD(Role)
