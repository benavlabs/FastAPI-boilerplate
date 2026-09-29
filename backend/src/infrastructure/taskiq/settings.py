"""Settings for the taskiq feature."""

from pydantic_settings import BaseSettings

from ..config.base import config
from ..config.enums import TaskiqBrokerType


class TaskiqSettings(BaseSettings):
    """Taskiq async task queue settings."""

    TASKIQ_ENABLED: bool = config("TASKIQ_ENABLED", default=True, cast=bool)
    TASKIQ_BROKER_TYPE: str = config("TASKIQ_BROKER_TYPE", default=TaskiqBrokerType.REDIS.value)

    TASKIQ_REDIS_HOST: str = config("TASKIQ_REDIS_HOST", default="localhost")
    TASKIQ_REDIS_PORT: int = config("TASKIQ_REDIS_PORT", default=6379, cast=int)
    TASKIQ_REDIS_DB: int = config("TASKIQ_REDIS_DB", default=3, cast=int)
    TASKIQ_REDIS_PASSWORD: str | None = config("TASKIQ_REDIS_PASSWORD", default=None)

    TASKIQ_RABBITMQ_HOST: str = config("TASKIQ_RABBITMQ_HOST", default="localhost")
    TASKIQ_RABBITMQ_PORT: int = config("TASKIQ_RABBITMQ_PORT", default=5672, cast=int)
    TASKIQ_RABBITMQ_USER: str = config("TASKIQ_RABBITMQ_USER", default="guest")
    TASKIQ_RABBITMQ_PASSWORD: str = config("TASKIQ_RABBITMQ_PASSWORD", default="guest")
    TASKIQ_RABBITMQ_VHOST: str = config("TASKIQ_RABBITMQ_VHOST", default="/")

    TASKIQ_WORKER_CONCURRENCY: int = config("TASKIQ_WORKER_CONCURRENCY", default=2, cast=int)
    TASKIQ_MAX_TASKS_PER_WORKER: int = config("TASKIQ_MAX_TASKS_PER_WORKER", default=1000, cast=int)

    @property
    def TASKIQ_BROKER_URL(self) -> str:
        """Generate broker URL based on configured backend."""
        if self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.REDIS.value:
            password_part = f":{self.TASKIQ_REDIS_PASSWORD}@" if self.TASKIQ_REDIS_PASSWORD else ""
            return f"redis://{password_part}{self.TASKIQ_REDIS_HOST}:{self.TASKIQ_REDIS_PORT}/{self.TASKIQ_REDIS_DB}"
        elif self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.RABBITMQ.value:
            vhost = self.TASKIQ_RABBITMQ_VHOST
            if vhost.startswith("/"):
                vhost = vhost[1:]
            return f"amqp://{self.TASKIQ_RABBITMQ_USER}:{self.TASKIQ_RABBITMQ_PASSWORD}@{self.TASKIQ_RABBITMQ_HOST}:{self.TASKIQ_RABBITMQ_PORT}/{vhost}"
        else:
            raise ValueError(f"Unsupported broker type: {self.TASKIQ_BROKER_TYPE}")
