from fastcrud import FastCRUD
from pydantic import BaseModel

from .models import Tier
from .schemas import TierCreateInternal, TierDelete, TierUpdate, TierUpdateInternal

crud_tiers = FastCRUD[Tier, TierCreateInternal, TierUpdate, TierUpdateInternal, TierDelete, BaseModel](Tier)
