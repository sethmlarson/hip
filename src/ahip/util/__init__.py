from __future__ import absolute_import

# For backwards compatibility, provide imports that used to be here.
from .connection import is_connection_dropped
from .request import make_headers
from .ssl_ import (
    SSLContext,
    HAS_SNI,
    IS_PYOPENSSL,
    IS_SECURETRANSPORT,
    assert_fingerprint,
    resolve_cert_reqs,
    resolve_ssl_version,
    ssl_wrap_socket,
    SSLWantReadError,
    SSLWantWriteError,
    PROTOCOL_TLS,
)
from .timeout import current_time, Timeout

from .retry import Retry
from .url import parse_url, Url
from .wait import wait_for_read, wait_for_write, wait_for_socket

__all__ = (
    "HAS_SNI",
    "IS_PYOPENSSL",
    "IS_SECURETRANSPORT",
    "SSLContext",
    "PROTOCOL_TLS",
    "Retry",
    "Timeout",
    "Url",
    "assert_fingerprint",
    "current_time",
    "is_connection_dropped",
    "parse_url",
    "make_headers",
    "resolve_cert_reqs",
    "resolve_ssl_version",
    "ssl_wrap_socket",
    "wait_for_read",
    "wait_for_write",
    "wait_for_socket",
    "SSLWantReadError",
    "SSLWantWriteError",
)
