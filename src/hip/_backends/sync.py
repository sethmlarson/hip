import errno
import socket
import typing
import ssl
import time

from .base import (
    AbortSendAndReceive,
    SocketOptionsType,
    is_writable,
    BlockedUntilNextRead,
)
from .wait import wait_for_socket
from hip.models import (
    TLSVersion,
    sslsocket_version_to_tls_version,
    alpn_to_http_version,
)
from hip import utils


class SyncBackend(object):
    def connect(
        self,
        host: str,
        port: int,
        connect_timeout: float,
        source_address: typing.Optional[typing.Tuple[str, int]] = None,
        socket_options: typing.Optional[SocketOptionsType] = None,
    ) -> "SyncSocket":
        conn = socket.create_connection(
            (host, port), connect_timeout, source_address=source_address,
        )
        for level, optname, value in socket_options or ():
            conn.setsockopt(level, optname, value)

        return SyncSocket(conn)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class SyncSocket(object):
    # _wait_for_socket is a hack for testing. See test_sync_connection.py for
    # the tests that use this.
    def __init__(
        self,
        sock: typing.Union[socket.socket, ssl.SSLSocket],
        _wait_for_socket=wait_for_socket,
    ):
        self._sock = sock
        # We keep the socket in non-blocking mode, except during connect() and
        # during the SSL handshake:
        self._sock.setblocking(False)
        self._wait_for_socket = _wait_for_socket

    def start_tls(
        self, server_hostname: str, ssl_context: ssl.SSLContext
    ) -> "SyncSocket":
        self._sock.setblocking(True)
        wrapped = ssl_context.wrap_socket(self._sock, server_hostname=server_hostname)
        wrapped.setblocking(False)
        return SyncSocket(wrapped)

    @typing.overload
    def getpeercert(self, binary_form: typing.Literal[True]) -> bytes:
        ...

    @typing.overload
    def getpeercert(self, binary_form: typing.Literal[False]) -> dict:
        ...

    # Only for SSL-wrapped sockets
    def getpeercert(self, binary_form: bool = False) -> typing.Union[bytes, dict]:
        return self._sock.getpeercert(binary_form=binary_form)

    def _wait(
        self, readable: bool, writable: bool, timeout: typing.Optional[float] = None
    ) -> None:
        assert readable or writable
        if not self._wait_for_socket(
            self._sock, read=readable, write=writable, timeout=timeout
        ):
            raise socket.timeout()  # XX use a backend-agnostic exception

    def send_all(self, data: bytes) -> None:
        while data:
            try:
                sent = self._sock.send(data)
                data = data[sent:]
            except ssl.SSLWantReadError:
                self._wait(readable=True, writable=False)
            except ssl.SSLWantWriteError:
                self._wait(readable=False, writable=True)
            except (OSError, socket.error) as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    self._wait(readable=False, writable=True)
                else:
                    raise

    def receive_some(self, read_timeout: typing.Optional[float]) -> bytes:
        while True:
            try:
                return self._sock.recv(utils.CHUNK_SIZE)
            except ssl.SSLWantReadError:
                self._wait(readable=True, writable=False, timeout=read_timeout)
            except ssl.SSLWantWriteError:
                self._wait(readable=False, writable=True, timeout=read_timeout)
            except (OSError, socket.error) as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    self._wait(readable=True, writable=False, timeout=read_timeout)
                else:
                    raise

    def send_and_receive_for_a_while(
        self,
        produce_bytes: typing.Callable[[], bytes],
        consume_bytes: typing.Callable[[bytes], None],
        read_timeout: float,
    ):
        outgoing_finished = False
        outgoing = b""
        waiting_for_read = False
        try:
            while True:
                if not outgoing_finished and not outgoing and not waiting_for_read:
                    # Can exit loop here with error
                    try:
                        b = produce_bytes()
                    except BlockedUntilNextRead:
                        waiting_for_read = True
                    else:
                        waiting_for_read = False
                        if b is None:
                            outgoing = None
                            outgoing_finished = True
                        else:
                            assert b
                            outgoing = memoryview(b)

                # This controls whether or not we block
                made_progress = False
                # If we do block, then these determine what can wake us up
                want_read = False
                want_write = False

                # Important: we do recv before send. This is because we want
                # to make sure that after a send completes, we immediately
                # call produce_bytes before calling recv and potentially
                # getting a LoopAbort. This avoids a race condition -- see the
                # "subtle invariant" in the backend API documentation.

                try:
                    incoming = self._sock.recv(utils.CHUNK_SIZE)
                except ssl.SSLWantReadError:
                    want_read = True
                except ssl.SSLWantWriteError:
                    want_write = True
                except (OSError, socket.error) as exc:
                    if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                        want_read = True
                    else:
                        raise
                else:
                    made_progress = True
                    waiting_for_read = False
                    # Can exit loop here with AbortSendAndReceive
                    consume_bytes(incoming)

                if outgoing and not outgoing_finished and not waiting_for_read:
                    try:
                        sent = self._sock.send(outgoing)
                        outgoing = outgoing[sent:]
                    except ssl.SSLWantReadError:
                        want_read = True
                    except ssl.SSLWantWriteError:
                        want_write = True
                    except (OSError, socket.error) as exc:
                        if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                            want_write = True
                        else:
                            raise
                    else:
                        made_progress = True

                if not made_progress:
                    self._wait(want_read, want_write, read_timeout)
        except AbortSendAndReceive:
            pass

    def http_version(self) -> typing.Optional[str]:
        if not hasattr(self._sock, "selected_alpn_protocol"):
            return None
        return alpn_to_http_version(self._sock.selected_alpn_protocol())

    def tls_version(self) -> typing.Optional[TLSVersion]:
        if not hasattr(self._sock, "version"):
            return None
        return sslsocket_version_to_tls_version(self._sock.version())

    def forceful_close(self) -> None:
        self._sock.close()

    def is_connected(self) -> bool:
        return is_writable(self._sock)

    def _getsockopt_tcp_nodelay(self) -> int:
        return self._sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)

    def getsockopt(self, level: int, option: int) -> int:
        return self._sock.getsockopt(level, option)

    def close(self) -> None:
        return self._sock.close()
