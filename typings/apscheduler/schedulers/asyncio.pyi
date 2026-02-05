# Type stubs for apscheduler.schedulers.asyncio
# Minimal stubs covering our usage of AsyncIOScheduler

from typing import Any, Callable  # noqa: UP035

from apscheduler.job import Job

class AsyncIOScheduler:
    """Async IO scheduler for APScheduler."""

    running: bool
    def __init__(self, **options: Any) -> None: ...
    def add_job(
        self,
        func: Callable[..., Any],
        trigger: str | None = None,
        args: list[Any] | tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        id: str | None = None,
        name: str | None = None,
        misfire_grace_time: int | None = None,
        coalesce: bool | None = None,
        max_instances: int | None = None,
        next_run_time: Any | None = None,
        jobstore: str = "default",
        executor: str = "default",
        replace_existing: bool = False,
        **trigger_args: Any,
    ) -> Job: ...
    def start(self, paused: bool = False) -> None: ...
    def shutdown(self, wait: bool = True) -> None: ...
    def remove_job(self, job_id: str, jobstore: str | None = None) -> None: ...
