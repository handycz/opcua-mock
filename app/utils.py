from typing import Callable

__all__ = ["lazyeval"]


class LazyEval:
    _callable: Callable[[], str]

    def __init__(self, func: Callable[[], str]):
        self._callable = func

    def __str__(self) -> str:
        return self._callable()


lazyeval = LazyEval
