import typing
import pathlib
import enum
import ssl

# TODO: Replace all these with real types
Headers = typing.Any
Request = typing.Any
Response = typing.Any
URL = typing.Any

PathType = typing.Union[str, pathlib.Path]
CACertsType = typing.Union[PathType, bytes]

class Origin:
    def __init__(self, scheme: str, host: str, port: int):
        self.scheme = scheme
        self.host = host
        self.port = port

class TLSVersion(enum.Enum):
    """Version specifier for TLS. Unless attempting to connect
    with only a single TLS version tls_maximum_version should
    be 'MAXIMUM_SUPPORTED'
    """

    MINIMUM_SUPPORTED = "MINIMUM_SUPPORTED"
    TLSv1 = "TLSv1"
    TLSv1_1 = "TLSv1.1"
    TLSv1_2 = "TLSv1.2"
    TLSv1_3 = "TLSv1.3"
    MAXIMUM_SUPPORTED = "MAXIMUM_SUPPORTED"

class TLSConfig:
    def __init__(
        self,
        trust_env: bool = True,
        ca_certs: typing.Optional[CACertsType] = None,
        pinned_certs: typing.Optional[typing.Dict[str, str]] = None,
        client_cert: typing.Optional[PathType] = None,
        client_key: typing.Optional[PathType] = None,
        client_key_password: typing.Optional[bytes] = None,
        tls_minimum_version: TLSVersion = TLSVersion.TLSv1_2,
        tls_maximum_version: TLSVersion = TLSVersion.MAXIMUM_SUPPORTED,
    ): ...
    def ssl_context(self, origin: Origin) -> ssl.SSLContext:
        """Creates an SSLContext object from the configuration given.
        If 'pinned_certs' is empty for the host then we can rely on OpenSSL
        verifying hostnames for us. Otherwise we need to verify hostnames
        for OpenSSL and fall-back on checking the fingerprint against the
        one we have pinned.
        """
    def verify_peercert(self, origin: Origin, peercert: bytes) -> None:
        """Callback that occurs after the handshake has happened from an SSLC. This allows
        the TLSConfig object to do verification after the handshake has completed.
        For example if no certificate matches within the trust store
        """
