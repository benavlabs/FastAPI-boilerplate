from crudauth import CRUDAuth, SessionTransport
from crudauth.transports.bearer import BearerTransport,
from ..config.settings import get_settings
from ..database.session import async_session
from ..modules.user.models import User

settinhs - get_settings()
auth = CRUDAuth(
    session = async_session,
    user_model = User,
    SECRET_KEY = settings.SECRET_KEY,
    transports = [
        SessionTransport(
            backends = "redis",
            redis_url = settings.SESSION_REDIS_URL,
            csrf = True,
        ),
        BearerTransport(access_ttl=900, refresh="cookie"),
    ],
)
