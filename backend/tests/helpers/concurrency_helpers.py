
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Callable, TypeVar

T = TypeVar("T")


def execute_concurrently(
    operation: Callable[[int], T],
    workers: int = 2,
) -> list[T]:
    """
    Execute operations concurrently.

    Each worker receives its own worker index.
    A barrier synchronizes execution before the operation starts.
    """

    barrier = Barrier(workers)

    def worker(index: int) -> T:
        barrier.wait(timeout=15)
        return operation(index)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(worker, index)
            for index in range(workers)
        ]

        return [future.result(timeout=60) for future in futures]
