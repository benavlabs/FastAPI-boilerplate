from fastcrud import FastCRUD

from ..db.token_blacklist import TokenBlackList
from ..schemas import TokenBlackListCreate, TokenBlackListRead, TokenBlackListUpdate

CRUDTokenBlackList = FastCRUD[
    TokenBlackList,
    TokenBlackListCreate,
    TokenBlackListUpdate,
    TokenBlackListUpdate,
    TokenBlackListUpdate,
    TokenBlackListRead,
]
crud_token_blacklist = CRUDTokenBlackList(TokenBlackList)
