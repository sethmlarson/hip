import threading
import typing


RetType = typing.TypeVar("RetType")
AsyncCallable = typing.Union[
    typing.Callable[[typing.Any], RetType],
    typing.Callable[[typing.Any], typing.Awaitable[RetType]],
]
SyncCallable = typing.Callable[[typing.Any], RetType]


def detect_is_async() -> typing.Union[typing.Literal[True], typing.Literal[False]]:
    """Tests if we're in the async part of the code or not"""

    async def f():
        """Unasync transforms async functions in sync functions"""
        return None

    obj = f()
    if obj is None:
        return typing.cast(typing.Literal[False], False)
    else:
        obj.close()  # prevent un-awaited coroutine warning
        return typing.cast(typing.Literal[True], True)


IS_ASYNC = detect_is_async()

T = typing.TypeVar("T")


async def iter_next(iterator: typing.AsyncIterator[T]) -> T:
    return await iterator.__anext__()


class SyncOnlyLock:
    """Acts like a threading.Lock() if being run in sync-mode, otherwise
    is a no-op. This is to handle threads compared to async code where
    threads have many 'heads' of execution whereas async has only a single
    'head' of execution.
    """

    def __init__(self):
        self.lock: typing.Optional[
            threading.Lock
        ] = None if IS_ASYNC else threading.Lock()

    def __enter__(self) -> "SyncOnlyLock":
        if self.lock:
            self.lock.acquire()
        return self

    def __exit__(self, *_: typing.Any) -> None:
        if self.lock:
            self.lock.release()


async def sync_or_async(
    f: AsyncCallable, *args: typing.Any, **kwargs: typing.Any
) -> RetType:
    ret = f(*args, **kwargs)
    if IS_ASYNC and hasattr(ret, "__await__"):
        ret = await ret
    return ret
