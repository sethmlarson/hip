import typing

if typing.TYPE_CHECKING:
    from .models import Request, Response


class HipError(Exception):
    """Base error type for 'Hip' which may carry the Request
    that initiated the lifecycle, the response at the end
    of the lifecycle, and the encapsulated error message if
    this error wraps a different exception.
    """

    def __init__(
        self,
        message: str,
        request: typing.Optional["Request"] = None,
        response: typing.Optional["Response"] = None,
        error: typing.Optional[Exception] = None,
    ):
        super().__init__(message)

        self.message = message
        self.request = request
        self.response = response
        self.error = error


class HTTPError(HipError):
    """Generic error relating to HTTP"""


class LocalProtocolError(HTTPError):
    """Error raised when the HTTP spec is violated locally"""


class RemoteProtocolError(HTTPError):
    """Error raised when the remote peer violates the HTTP spec"""


class ResponseBodyConsumed(HTTPError):
    """Error raised when attempting to stream from a Response multiple times"""


class TimeoutError(HipError):
    """Error raised when an operation times out"""


class ReadTimeout(TimeoutError):
    """Error raised when reading from a socket times out"""


class ConnectTimeout(TimeoutError):
    """Error raised when a socket connection times out"""


class RedirectLoopDetected(HTTPError):
    """Error raised when a redirect is received to a URL
    that was previously redirected to
    """


class TooManyRedirects(HTTPError):
    """Error raised when the number of redirects exceeds the maximum"""


class TooManyRetries(HTTPError):
    """Error raised when the number of retries exceeds the maximum"""


class UnrewindableBodyError(HipError):
    """Error raised when a request needs to be sent again due to retry
    but the request body cannot be rewound.
    """


class CannotRetryUnsafeRequest(HTTPError):
    """Error raised when a request that is not marked as 'safe' to retry
    fails in a way that is otherwise retryable.
    """


class ConnectionError(HipError):
    """Generic error raised while attempting to setup a connection"""


class NameResolutionError(ConnectionError):
    """Error raised when DNS fails to resolve a hostname"""


class ProxyError(ConnectionError):
    """Error raised when a proxy fails to establish a connection"""


class TLSError(ConnectionError):
    """Generic error related to the TLS protocol"""


class TLSVersionNotSupported(TLSError):
    """The remote server doesn't support a TLS version
    within the currently specified min / max
    """


class CertificateError(ConnectionError):
    """Generic error related to certificate verification"""


class CertificateHostnameMismatch(CertificateError):
    """Certificate was valid but didn't have the correct
    'subjectAltName' or 'commonName' (if no subjectAltName)
    """


class SelfSignedCertificate(CertificateError):
    """Certificate was self-signed, can't verify unless
    used with 'pinned_certs=...'
    """


class CertificateFingerprintMismatch(CertificateError):
    """The certificate fingerprint doesn't match the previous value."""


class URLError(HipError):
    """Error while parsing a URL"""
