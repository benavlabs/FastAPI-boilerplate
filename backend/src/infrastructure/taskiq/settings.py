"""Settings for the taskiq feature."""

from urllib.parse import quote

from sqlalchemy.engine import URL

from ..config.base import EnvSettings
from ..config.enums import TaskiqBrokerType
from ..redis import redis_url


class TaskiqSettings(EnvSettings):
    """Taskiq async task queue settings."""

    TASKIQ_BROKER_TYPE: str = TaskiqBrokerType.REDIS.value
    TASKIQ_DEFAULT_RETRY_COUNT: int = 3
    TASKIQ_RETRY_DELAY_SECONDS: int = 0

    TASKIQ_REDIS_HOST: str = "localhost"
    TASKIQ_REDIS_PORT: int = 6379
    TASKIQ_REDIS_DB: int = 3
    TASKIQ_REDIS_PASSWORD: str | None = None

    TASKIQ_RABBITMQ_HOST: str = "localhost"
    TASKIQ_RABBITMQ_PORT: int = 5672
    TASKIQ_RABBITMQ_USER: str = "guest"
    TASKIQ_RABBITMQ_PASSWORD: str = "guest"
    TASKIQ_RABBITMQ_VHOST: str = "/"

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
