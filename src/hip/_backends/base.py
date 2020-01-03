import contextlib
import typing
import ssl
import socket
from .wait import wait_for_read, wait_for_write
from hip.models import TLSVersion, peercert_info
from hip.exceptions import (
    ReadTimeout,
    ConnectTimeout,
    TLSError,
    CertificateError,
    CertificateHostnameMismatch,
    SelfSignedCertificate,
    NameResolutionError,
    ExpiredCertificate,
)


SocketOptionsType = typing.Iterable[typing.Tuple[int, int, int]]


class AbortSendAndReceive(Exception):
    """Exception that signals Socket.send_and_receive_for_a_while() to abort."""


class BlockedUntilNextRead(Exception):
    """Exception that signals that 'produce_bytes()' cannot continue until data is read."""


def is_readable(sock: socket.socket) -> bool:
    return wait_for_read(sock, timeout=0)


def is_writable(sock: socket.socket) -> bool:
    return wait_for_write(sock, timeout=0)


@contextlib.contextmanager
def wrap_exceptions(sock: typing.Any, is_connect: bool) -> None:
    """Wraps socket and TLS exceptions into hip.HipErrors.
    These are especially helpful for TLS and certificate errors
    because we can point to documentation on how to handle these
    exceptions and help users make good security decisions.
    """

    def rewrite_exception(err: Exception) -> None:
        nonlocal is_connect

        try:
            # Try to extract the inner exception from a trio.BrokenResourceError
            # if trio support exists. If the user doesn't have trio installed
            # we need to fail gracefully, can't assume their backend.
            import trio

            if isinstance(err, trio.BrokenResourceError):
                err = err.__cause__
        except ImportError:
            pass

        if isinstance(err, socket.gaierror):
            raise NameResolutionError("dns error") from err
        elif isinstance(err, socket.timeout):
            if is_connect:
                raise ConnectTimeout("connect timeout", error=err) from err
            else:
                raise ReadTimeout("read timeout", error=err) from err
        elif isinstance(err, ssl.SSLCertVerificationError):
            msg = str(err).lower()
            if "self" in msg and "signed" in msg:
                raise SelfSignedCertificate("self signed", error=err) from err
            elif "hostname" in msg and "mismatch" in msg:
                raise CertificateHostnameMismatch(
                    "hostname mismatch", error=err
                ) from err
            elif "expired" in msg:
                raise ExpiredCertificate("cert is expired", error=err) from err
            else:
                raise CertificateError("cert error", error=err) from err
        elif isinstance(err, ssl.SSLError):
            raise TLSError("tls error", error=err) from err

    try:
        yield
    except Exception as err:
        rewrite_exception(err)
        # This ensures that if the exception wasn't rewritten
        # that we don't swallow the exception.
        raise err from err


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

    def create_queue(self, size: int) -> "AsyncQueue":
        ...


class AsyncQueue:
    def __init__(self, size: int):
        ...

    async def put(self, item: typing.Any) -> None:
        ...

    def put_nowait(self, item: typing.Any) -> None:
        ...

    async def get(self) -> typing.Any:
        ...

    def get_nowait(self) -> typing.Any:
        ...


class AsyncSocket:
    async def start_tls(
        self, server_hostname: str, ssl_context: ssl.SSLContext
    ) -> "AsyncSocket":
        raise NotImplementedError()

    @typing.overload
    def getpeercert(self, binary_form: typing.Literal[True]) -> typing.Optional[bytes]:
        ...

    @typing.overload
    def getpeercert(
        self, binary_form: typing.Literal[False]
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        ...

    def getpeercert(
        self, binary_form: bool = False
    ) -> typing.Optional[typing.Union[bytes, typing.Dict[str, typing.Any]]]:
        raise NotImplementedError()

    def selected_alpn_protocol(self) -> typing.Optional[str]:
        raise NotImplementedError()

    def version(self) -> typing.Optional[str]:
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

    def is_connected(self) -> bool:
        raise NotImplementedError()

    def http_version(self) -> typing.Optional[str]:
        raise NotImplementedError()

    def tls_version(self) -> typing.Optional[TLSVersion]:
        raise NotImplementedError()
