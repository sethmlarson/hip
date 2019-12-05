import sniffio
import typing
from .base import AsyncSocket, AsyncBackend, AbortSendAndReceive
from .sync import SyncSocket, SyncBackend
from .trio import TrioBackend

__all__ = [
    "AsyncSocket",
    "SyncSocket",
    "AsyncBackend",
    "SyncBackend",
    "AbortSendAndReceive",
]


@typing.overload
def get_backend(is_async: typing.Literal[True]) -> AsyncBackend:
    ...


@typing.overload
def get_backend(is_async: typing.Literal[False]) -> SyncBackend:
    ...


def get_backend(is_async: bool) -> typing.Union[AsyncBackend, SyncBackend]:
    """Gets the backend according to whether an async/sync backend
    is requested and if async by what event loop is currently active.
    """
    if is_async:
        try:
            async_lib = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            raise ValueError("?") from None
        if async_lib == "trio":
            return TrioBackend()
        else:
            raise ValueError("?")
    else:
        return SyncBackend()
