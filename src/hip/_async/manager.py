import ssl
import socket
import contextlib
import typing
from hip.models import (
    Origin,
    LiteralTLSVersionType,
    CACertsType,
    create_ssl_context,
    verify_peercert_fingerprint,
)
from hip.exceptions import (
    NameResolutionError,
    TLSError,
    TLSVersionNotSupported,
    CertificateError,
)
from hip._backends import get_backend, AsyncBackend, AsyncSocket
from .models import IS_ASYNC
from .http1 import HTTPTransaction, HTTP11Transaction


class ConnectionConfig(typing.NamedTuple):
    """Represents a request for a connection from a Session"""

    origin: Origin
    http_versions: typing.Sequence[str]
    ca_certs: typing.Optional[CACertsType]
    pinned_cert: typing.Optional[typing.Tuple[str, str]]
    tls_min_version: LiteralTLSVersionType
    tls_max_version: LiteralTLSVersionType

    def match(self, conn_key: "ConnectionKey") -> bool:
        return all(
            (
                self.origin == conn_key.origin,
                self.ca_certs == conn_key.ca_certs,
                self.pinned_cert == conn_key.pinned_cert,
                conn_key.http_version in self.http_versions,
                (
                    conn_key.tls_version is None
                    or (
                        self.tls_min_version.value
                        <= conn_key.tls_version.value
                        <= self.tls_max_version.value,
                    )
                ),
            )
        )


class ConnectionKey(typing.NamedTuple):
    """Represents a connection within the pool"""

    origin: Origin
    http_version: str
    ca_certs: typing.Optional[CACertsType]
    pinned_cert: typing.Optional[typing.Tuple[str, str]]
    tls_version: LiteralTLSVersionType


class BackgroundManager:
    def __init__(self):
        self.backend: AsyncBackend = get_backend(IS_ASYNC)
        self.pool: typing.Dict[ConnectionKey, AsyncSocket] = {}

    async def start_http_transaction(
        self, conn_config: ConnectionConfig
    ) -> HTTPTransaction:
        with self._wrap_exceptions(conn_config):
            socket = await self._get_socket(conn_config)
            return HTTP11Transaction(socket)

    async def _get_socket(self, conn_config: ConnectionConfig) -> AsyncSocket:
        socket = None
        to_pop = []
        for conn_key, sock in self.pool.items():
            if conn_config.match(conn_key):
                if not sock.is_connected():
                    to_pop.append(conn_key)
                else:
                    socket = sock
                    break

        for conn_key in to_pop:
            self.pool.pop(conn_key)

        return socket or (await self._new_socket(conn_config))

    async def _new_socket(self, conn_config: ConnectionConfig) -> AsyncSocket:
        scheme, host, port = conn_config.origin
        socket = await self.backend.connect(host, port, connect_timeout=10.0)

        if scheme == "https":
            ctx = create_ssl_context(
                ca_certs=conn_config.ca_certs,
                pinned_cert=conn_config.pinned_cert,
                http_versions=conn_config.http_versions,
                tls_min_version=conn_config.tls_min_version,
                tls_max_version=conn_config.tls_max_version,
            )

            socket = await socket.start_tls(server_hostname=host, ssl_context=ctx)

            if conn_config.pinned_cert:
                verify_peercert_fingerprint(
                    peercert=socket.getpeercert(binary_form=True),
                    pinned_cert=conn_config.pinned_cert,
                )

        http_version = socket.http_version()
        tls_version = socket.tls_version()
        conn_key = ConnectionKey(
            conn_config.origin,
            http_version=http_version,
            ca_certs=conn_config.ca_certs,
            pinned_cert=conn_config.pinned_cert,
            tls_version=tls_version,
        )
        self.pool[conn_key] = socket
        return socket

    @contextlib.contextmanager
    def _wrap_exceptions(self, conn_config: ConnectionConfig):
        scheme, host, port = conn_config.origin
        try:
            yield
        except socket.gaierror as e:
            raise NameResolutionError(
                f"could not resolve hostname '{host}:{port}'", error=e
            )
