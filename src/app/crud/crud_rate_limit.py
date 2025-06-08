from fastcrud import FastCRUD

from ..models.rate_limit import RateLimit
from ..schemas.rate_limit import (
    RateLimitCreateInternal,
    RateLimitDelete,
    RateLimitRead,
    RateLimitUpdate,
    RateLimitUpdateInternal,
)

CRUDRateLimit = FastCRUD[
    RateLimit, RateLimitCreateInternal, RateLimitUpdate, RateLimitUpdateInternal, RateLimitDelete, RateLimitRead
]
crud_rate_limits = CRUDRateLimit(RateLimit)
