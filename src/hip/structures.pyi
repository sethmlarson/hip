import typing
from .models import TLSVersion, PathType, CACertsType, Headers, Origin, URL

TLSSessionTicket = typing.Any

class ConnectionKey(typing.NamedTuple):
    """A key that uniquely identifies an HTTP connection
    created from a 'ConnectionConfig'. Almost identical to
    'ConnectionConfig' except that ranges of values like
    'tls_minimum_version + tls_maximum_version', 'pinned_certs'
    and 'tls_alpn_protocols' are collapsed to a single values:
    'tls_version', 'pinned_cert', and 'tls_alpn_protocol'.
    """

    session_id: int
    origin: Origin
    ca_certs: typing.Optional[CACertsType]
    pinned_cert: typing.Optional[typing.Tuple[str, str]]
    client_cert: typing.Optional[PathType]
    client_key: typing.Optional[PathType]
    client_password: typing.Optional[bytes]
    tls_version: typing.Optional[TLSVersion]
    tls_alpn_protocol: str
    tls_server_hostname: typing.Optional[str]
    tls_session_ticket: typing.Optional[TLSSessionTicket]
    proxy_url: typing.Optional[URL]
    proxy_headers: typing.Optional[Headers]

class ConnectionConfig(typing.NamedTuple):
    """Config that identifies a desired HTTP connection
    requested by a Session.

    If no sensitive information is passed we can use
    'session_id=0' which means the connection can be
    shared with other sessions. If any of the following
    conditions become true then a connection should be
    allocated the id of the session currently using it
    so that it stays private to that session:

    - Non-null client_cert / client_key / client_password
    - Successful TLS session resumption
    - Any of the following headers are sent by the client:
      - 'Cookie'
      - 'Authorization'
      - 'Proxy-Authorization'
    - Any of the following headers are sent by the server:
      - 'Set-Cookie'
    - If 'auth' is non-null on Session.prepare_request()

    All values must be exact matches except for:
    - pinned_certs
    - tls_min_version
    - tls_max_version
    - tls_alpn_protocols
    which match differently
    """

    session_id: int
    origin: Origin
    ca_certs: typing.Optional[CACertsType]
    pinned_certs: typing.Dict[str, str]
    client_cert: typing.Optional[PathType]
    client_key: typing.Optional[PathType]
    client_password: typing.Optional[bytes]
    tls_min_version: typing.Optional[TLSVersion]
    tls_max_version: typing.Optional[TLSVersion]
    tls_alpn_protocols: typing.Tuple[str, ...]
    tls_server_hostname: typing.Optional[str]
    tls_session_ticket: typing.Optional[TLSSessionTicket]
    proxy_url: typing.Optional[URL]
    proxy_headers: typing.Optional[Headers]
