from fastcrud import FastCRUD
from pydantic import BaseModel

from .models import RateLimit
from .schemas import RateLimitCreateInternal, RateLimitDelete, RateLimitUpdate, RateLimitUpdateInternal

crud_rate_limits = FastCRUD[
    RateLimit, RateLimitCreateInternal, RateLimitUpdate, RateLimitUpdateInternal, RateLimitDelete, BaseModel
](RateLimit)
