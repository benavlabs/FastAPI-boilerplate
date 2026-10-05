"""Settings for the taskiq feature."""

from urllib.parse import quote

from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL

from ..config.base import config
from ..config.enums import TaskiqBrokerType
from ..redis import redis_url


class TaskiqSettings(BaseSettings):
    """Taskiq async task queue settings."""

    TASKIQ_BROKER_TYPE: str = config("TASKIQ_BROKER_TYPE", default=TaskiqBrokerType.REDIS.value)
    TASKIQ_DEFAULT_RETRY_COUNT: int = config("TASKIQ_DEFAULT_RETRY_COUNT", default=3, cast=int)

    TASKIQ_REDIS_HOST: str = config("TASKIQ_REDIS_HOST", default="localhost")
    TASKIQ_REDIS_PORT: int = config("TASKIQ_REDIS_PORT", default=6379, cast=int)
    TASKIQ_REDIS_DB: int = config("TASKIQ_REDIS_DB", default=3, cast=int)
    TASKIQ_REDIS_PASSWORD: str | None = config("TASKIQ_REDIS_PASSWORD", default=None)

    TASKIQ_RABBITMQ_HOST: str = config("TASKIQ_RABBITMQ_HOST", default="localhost")
    TASKIQ_RABBITMQ_PORT: int = config("TASKIQ_RABBITMQ_PORT", default=5672, cast=int)
    TASKIQ_RABBITMQ_USER: str = config("TASKIQ_RABBITMQ_USER", default="guest")
    TASKIQ_RABBITMQ_PASSWORD: str = config("TASKIQ_RABBITMQ_PASSWORD", default="guest")
    TASKIQ_RABBITMQ_VHOST: str = config("TASKIQ_RABBITMQ_VHOST", default="/")

    @property
    def TASKIQ_BROKER_URL(self) -> str:
        """Generate broker URL based on configured backend."""
        if self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.REDIS.value:
            return redis_url(self.TASKIQ_REDIS_HOST, self.TASKIQ_REDIS_PORT, self.TASKIQ_REDIS_DB, self.TASKIQ_REDIS_PASSWORD)
        elif self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.RABBITMQ.value:
            return URL.create(
                drivername="amqp",
                username=self.TASKIQ_RABBITMQ_USER,
                password=self.TASKIQ_RABBITMQ_PASSWORD,
                host=self.TASKIQ_RABBITMQ_HOST,
                port=self.TASKIQ_RABBITMQ_PORT,
                database=quote(self.TASKIQ_RABBITMQ_VHOST.lstrip("/"), safe=""),
            ).render_as_string(hide_password=False)
        else:
            raise ValueError(f"Unsupported broker type: {self.TASKIQ_BROKER_TYPE}")
