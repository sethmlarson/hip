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
    with only a single TLS version tls_max_version should
    be 'MAX_SUPPORTED'
    """

    MIN_SUPPORTED = "MIN_SUPPORTED"
    TLSv1 = "TLSv1"
    TLSv1_1 = "TLSv1.1"
    TLSv1_2 = "TLSv1.2"
    TLSv1_3 = "TLSv1.3"
    MAX_SUPPORTED = "MAX_SUPPORTED"
