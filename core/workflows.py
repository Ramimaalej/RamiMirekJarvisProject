from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("workflows")

DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY = 3
TOOL_TIMEOUT = 180


def tool_task(
    fn: Callable | None = None,
    *,
    retries: int = DEFAULT_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    timeout_seconds: int = TOOL_TIMEOUT,
    name: str | None = None,
):
    """Decorator that wraps a tool function as a Prefect task with retry + timeout."""
    from prefect import task
    from prefect.logging import get_run_logger
    def decorator(func: Callable) -> Callable:
        @task(
            name=name or func.__name__,
            retries=retries,
            retry_delay_seconds=retry_delay,
            timeout_seconds=timeout_seconds,
            log_prints=True,
        )
        def wrapper(*args, **kwargs) -> Any:
            log = get_run_logger()
            log.info("Running %s", func.__name__)
            try:
                result = func(*args, **kwargs)
                log.info("%s completed", func.__name__)
                return result
            except Exception as e:
                log.error("%s failed: %s", func.__name__, e)
                raise
        return wrapper
    return decorator if fn is None else decorator(fn)


def agent_flow(
    fn: Callable | None = None,
    *,
    name: str | None = None,
    retries: int = 0,
    timeout_seconds: int = 600,
):
    """Decorator that wraps an agent execution as a Prefect flow."""
    from prefect import flow
    from prefect.logging import get_run_logger
    from prefect.task_runners import ConcurrentTaskRunner
    def decorator(func: Callable) -> Callable:
        @flow(
            name=name or func.__name__,
            retries=retries,
            timeout_seconds=timeout_seconds,
            log_prints=True,
            task_runner=ConcurrentTaskRunner(),
        )
        def wrapper(*args, **kwargs) -> Any:
            log = get_run_logger()
            log.info("Flow %s started", func.__name__)
            try:
                result = func(*args, **kwargs)
                log.info("Flow %s completed", func.__name__)
                return result
            except Exception as e:
                log.error("Flow %s failed: %s", func.__name__, e)
                raise
        return wrapper
    return decorator if fn is None else decorator(fn)


def step_task(
    *,
    retries: int = 2,
    retry_delay: int = 3,
    timeout_seconds: int = 180,
):
    """Decorator for individual agent execution steps with retry policy."""
    from prefect import task
    from prefect.logging import get_run_logger
    def decorator(func: Callable) -> Callable:
        @task(
            name=func.__name__,
            retries=retries,
            retry_delay_seconds=retry_delay,
            timeout_seconds=timeout_seconds,
            log_prints=True,
            tags=["agent_step"],
        )
        def wrapper(*args, **kwargs) -> Any:
            log = get_run_logger()
            step_num = kwargs.get("step_num", "?")
            tool = kwargs.get("tool", "?")
            log.info("Step %s [%s] starting", step_num, tool)
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                log.info("Step %s [%s] done in %.1fs", step_num, tool, elapsed)
                return result
            except Exception as e:
                elapsed = time.time() - start
                log.error("Step %s [%s] failed after %.1fs: %s", step_num, tool, elapsed, e)
                raise
        return wrapper
    return decorator


def schedule_flow(
    fn: Callable | None = None,
    *,
    name: str | None = None,
    retries: int = 1,
    timeout_seconds: int = 300,
):
    """Decorator for scheduled job execution flows."""
    from prefect import flow
    from prefect.logging import get_run_logger
    def decorator(func: Callable) -> Callable:
        @flow(
            name=name or func.__name__,
            retries=retries,
            timeout_seconds=timeout_seconds,
            log_prints=True,
        )
        def wrapper(*args, **kwargs) -> Any:
            log = get_run_logger()
            job_name = kwargs.get("job_name", "unknown")
            log.info("Scheduled job '%s' running", job_name)
            try:
                result = func(*args, **kwargs)
                log.info("Scheduled job '%s' completed", job_name)
                return result
            except Exception as e:
                log.error("Scheduled job '%s' failed: %s", job_name, e)
                raise
        return wrapper
    return decorator if fn is None else decorator(fn)
