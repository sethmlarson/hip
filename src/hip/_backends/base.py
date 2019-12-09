import typing
import ssl
import socket
from .wait import wait_for_read


SocketOptionsType = typing.Iterable[typing.Tuple[int, int, int]]


class AbortSendAndReceive(Exception):
    """Exception that signals Socket.send_and_receive_for_a_while() to abort."""


class BlockedUntilNextRead(Exception):
    """Exception that signals that 'produce_bytes()' cannot continue until data is read."""


def is_readable(sock: socket.socket) -> bool:
    return wait_for_read(sock, timeout=0)


class AsyncBackend:
    async def connect(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float,
        source_address: typing.Optional[str] = None,
        socket_options: typing.Optional[
            typing.Iterable[typing.Tuple[int, int, int]]
        ] = None
    ) -> "AsyncSocket":
        ...

    async def sleep(self, seconds: float) -> None:
        ...


class AsyncSocket:
    async def start_tls(
        self, server_hostname: str, ssl_context: ssl.SSLContext
    ) -> "AsyncSocket":
        raise NotImplementedError()

    @typing.overload
    def getpeercert(self, binary_form: typing.Literal[True]) -> bytes:
        ...

    @typing.overload
    def getpeercert(self, binary_form: typing.Literal[False]) -> dict:
        ...

    def getpeercert(self, binary_form: bool = False) -> typing.Union[bytes, dict]:
        raise NotImplementedError()

    async def send_all(self, data: bytes) -> None:
        raise NotImplementedError()

    async def receive_some(self) -> bytes:
        raise NotImplementedError()

    async def send_and_receive_for_a_while(
        self,
        produce_bytes: typing.Callable[[], typing.Awaitable[bytes]],
        consume_bytes: typing.Callable[[bytes], None],
        read_timeout: float,
    ) -> None:
        raise NotImplementedError()

    def forceful_close(self) -> None:
        raise NotImplementedError()

    def is_readable(self) -> bool:
        raise NotImplementedError()
