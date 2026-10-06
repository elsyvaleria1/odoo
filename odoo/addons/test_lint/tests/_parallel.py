import functools
import logging
import os
from collections.abc import Callable, Hashable, Sequence
from concurrent.futures import ProcessPoolExecutor

_logger = logging.getLogger(__name__)

_SERIAL_BELOW = 500


def job_count(work: int) -> int:
    override = os.environ.get("TEST_LINT_JOBS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            _logger.warning(
                "TEST_LINT_JOBS=%r is not a number, working serially", override
            )
            return 1
    if work < _SERIAL_BELOW:
        return 1
    return max(1, min(16, (os.process_cpu_count() or 1) - 2))


def _stop_multiprocessing_helpers() -> None:
    import multiprocessing.forkserver
    import multiprocessing.resource_tracker

    for holder in (
        getattr(multiprocessing.forkserver, "_forkserver", None),
        getattr(multiprocessing.resource_tracker, "_resource_tracker", None),
    ):
        stop = getattr(holder, "_stop", None)
        if stop is None:
            continue
        try:
            stop()
        except Exception:
            _logger.debug("could not stop a multiprocessing helper", exc_info=True)


def run_chunks[T, R](
    function: Callable[[list[T]], R], items: Sequence[T], jobs: int
) -> list[R]:
    # Strided chunks spread the large files of one addon over every worker.
    stride = jobs * 4
    chunks = [list(items[index::stride]) for index in range(stride)]
    try:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            return list(pool.map(function, chunks))
    finally:
        _stop_multiprocessing_helpers()


def map_chunks[T, R](
    function: Callable[[list[T]], R], items: Sequence[T]
) -> tuple[list[R], int]:
    jobs = job_count(len(items))
    if jobs > 1:
        try:
            return run_chunks(function, items, jobs), jobs
        except Exception:
            _logger.warning(
                "parallel run of %s unavailable, falling back to a serial one",
                getattr(function, "__qualname__", function),
                exc_info=True,
            )
    return [function(list(items))], 1


def _apply_each[K: Hashable, R](
    function: Callable[[K], R], chunk: list[K]
) -> list[tuple[K, R]]:
    return [(item, function(item)) for item in chunk]


def map_items[K: Hashable, R](
    function: Callable[[K], R], items: Sequence[K]
) -> dict[K, R]:
    # A worker is a fresh interpreter: `function` is imported by name there and
    # sees neither the configured addons path nor the registry.
    parts, jobs = map_chunks(functools.partial(_apply_each, function), items)
    _logger.debug(
        "%s over %s item(s) in %s process(es)",
        getattr(function, "__qualname__", function),
        len(items),
        jobs,
    )
    return {item: result for part in parts for item, result in part}
