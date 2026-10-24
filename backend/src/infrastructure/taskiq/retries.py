"""How a task that asks to be retried is retried, and where a delayed retry waits."""

from taskiq import AsyncBroker, ScheduleSource, TaskiqMiddleware
from taskiq.middlewares import SimpleRetryMiddleware, SmartRetryMiddleware
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListRedisScheduleSource

from ..config.enums import TaskiqBrokerType
from ..config.settings import get_settings
from .constants import RETRY_MAX_DELAY_SECONDS, RETRY_SCHEDULE_PREFIX

settings = get_settings()


def retry_schedule_source() -> ScheduleSource | None:
    """Where a delayed retry waits until it is due, or ``None`` where retries are immediate.

    A broker holds the messages it is given now; a message due later has to be held
    somewhere a scheduler reads, which is what this is.

    Raises:
        ValueError: A delay is configured for a broker there is no such place for.
    """
    if settings.TASKIQ_RETRY_DELAY_SECONDS <= 0:
        return None

    if settings.TASKIQ_BROKER_TYPE != TaskiqBrokerType.REDIS.value:
        raise ValueError(
            f"TASKIQ_RETRY_DELAY_SECONDS holds each retry in a Redis schedule source, and the "
            f"{settings.TASKIQ_BROKER_TYPE!r} broker is configured with no Redis to hold it in. "
            f"Leave the delay at 0 to retry immediately, or run the queue on redis."
        )

    return ListRedisScheduleSource(url=settings.TASKIQ_BROKER_URL, prefix=RETRY_SCHEDULE_PREFIX)


def retry_middleware(holding: ScheduleSource | None) -> TaskiqMiddleware:
    """The middleware that retries a task labelled ``retry_on_error=True``.

    With no ``holding`` a retry is requeued the moment the task fails, so a task tripped up
    by something that lasts a few seconds spends every attempt inside those seconds.

    With one, each retry is scheduled instead: the first waits
    ``TASKIQ_RETRY_DELAY_SECONDS``, each one after waits longer up to
    ``RETRY_MAX_DELAY_SECONDS``, and jitter keeps a queue of them from coming back
    together. That takes a scheduler running next to the worker, since the scheduler is
    what reads the schedules and enqueues them when they are due.
    """
    if holding is None:
        return SimpleRetryMiddleware(default_retry_count=settings.TASKIQ_DEFAULT_RETRY_COUNT)

    return SmartRetryMiddleware(
        default_retry_count=settings.TASKIQ_DEFAULT_RETRY_COUNT,
        default_delay=settings.TASKIQ_RETRY_DELAY_SECONDS,
        use_delay_exponent=True,
        max_delay_exponent=RETRY_MAX_DELAY_SECONDS,
        use_jitter=True,
        schedule_source=holding,
    )


def schedule_sources(broker: AsyncBroker) -> list[ScheduleSource]:
    """Everything the scheduler reads schedules from: the task labels, and delayed retries.

    A retry is scheduled by the worker and read by the scheduler, so a project that
    configures a delay and runs no scheduler has retries that never run.
    """
    sources: list[ScheduleSource] = [LabelScheduleSource(broker)]
    holding = retry_schedule_source()
    if holding is not None:
        sources.append(holding)

    return sources
