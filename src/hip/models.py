import binascii
import ssl
import typing
import os
import enum
import secrets
import codecs
import pathlib
import hmac
import hashlib
from .utils import parse_mimetype, is_known_encoding, pretty_fingerprint, none_is_inf
from .exceptions import HTTPError, CertificateFingerprintMismatch


PathType = typing.Union[str, pathlib.Path]
CACertsType = typing.Union[PathType, bytes]
PinnedCertsType = typing.Mapping[str, str]
TimeoutType = typing.Any
RetriesType = typing.Union[int, "Retry"]
RedirectsType = typing.Union[bool, int]
HeadersType = typing.Union[
    typing.Mapping[str, typing.Optional[str]],
    typing.Mapping[bytes, typing.Optional[bytes]],
    typing.Iterable[typing.Tuple[str, typing.Optional[str]]],
    typing.Iterable[typing.Tuple[bytes, typing.Optional[bytes]]],
    "Headers",
]
URLType = typing.Union[str, "URL"]
ProxiesType = typing.Mapping[str, URLType]
CookiesType = typing.Mapping[str, str]

REDIRECT_STATUSES = {
    301,  # Moved Permanently
    302,  # Found
    303,  # See Other
    307,  # Temporary Redirect
    308,  # Permanent Redirect
}


class _ParamNoValue(object):
    def __bool__(self) -> bool:
        # We want this sentinel to evaluate as 'falsy'
        return False

    def __repr__(self) -> str:
        return "hip.PARAM_NO_VALUE"

    __str__ = __repr__

    def __eq__(self, other: typing.Any) -> bool:
        return other is PARAM_NO_VALUE and self is PARAM_NO_VALUE

    def __ne__(self, other: typing.Any) -> bool:
        return other is not PARAM_NO_VALUE or self is not PARAM_NO_VALUE


PARAM_NO_VALUE = _ParamNoValue()
ParamsValueType = typing.Optional[typing.Union[str, _ParamNoValue]]
ParamsType = typing.Union[
    typing.Sequence[typing.Tuple[str, ParamsValueType]],
    typing.Mapping[str, typing.Optional[ParamsValueType]],
]


class Origin(typing.NamedTuple):
    scheme: str
    host: str
    port: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Origin):
            return NotImplemented
        return (
            self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, Origin):
            return NotImplemented
        return not self == other


class URL:
    DEFAULT_PORT_BY_SCHEME: typing.Dict[str, int] = {
        "http": 80,
        "https": 443,
    }

    def __init__(
        self,
        url: typing.Optional[URLType] = None,
        *,
        scheme: typing.Optional[str] = None,
        username: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        host: typing.Optional[str] = None,
        port: typing.Optional[int] = None,
        path: typing.Optional[typing.Union[str, typing.Sequence[str]]] = None,
        params: typing.Optional[typing.Any] = None,
        fragment: typing.Optional[str] = None,
    ):
        self.scheme = scheme
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.path = path
        self.params = params
        self.fragment = fragment

    @property
    def origin(self) -> Origin:
        if self.scheme is None or self.host is None:
            raise HTTPError("Origin cannot be determined for non-absolute URLs")
        if self.port is None:
            if self.scheme not in self.DEFAULT_PORT_BY_SCHEME:
                raise HTTPError(f"Unknown default port for scheme '{self.scheme}'")
            port = self.DEFAULT_PORT_BY_SCHEME[self.scheme]
        else:
            port = self.port
        return Origin(self.scheme, self.host, port)

    def join(self, url: URLType) -> "URL":
        ...


KT = typing.TypeVar("KT")
VT = typing.TypeVar("VT")
NormKT = typing.TypeVar("NormKT")
NormVT = typing.TypeVar("NormVT")
MultiMappingType = typing.Union[
    typing.Mapping[KT, VT], typing.Sequence[typing.Tuple[KT, VT]]
]


class MultiMapping(typing.Generic[KT, VT, NormKT, NormVT]):
    def __init__(self, values: MultiMappingType = ()):
        self._internal: typing.Dict[
            NormKT, typing.List[typing.Tuple[NormKT, NormVT]]
        ] = {}
        if values:
            self.extend(values)

    def get_one(
        self, key: KT, default: typing.Optional[NormVT] = None
    ) -> typing.Optional[NormVT]:
        try:
            return self._internal[self._normalize_key(key)][0][1]
        except (KeyError, IndexError):
            return default

    get = get_one

    def get_all(self, key: KT) -> typing.List[NormVT]:
        try:
            return [x[1] for x in self._internal[self._normalize_key(key)]]
        except KeyError:
            return []

    def pop_one(
        self, key: KT, default: typing.Optional[VT] = None
    ) -> typing.Optional[NormVT]:
        try:
            items = self._internal[self._normalize_key(key)]
            return items.pop(0)[1]
        except (KeyError, IndexError):
            return default

    pop = pop_one

    def pop_all(self, key: KT) -> typing.List[NormVT]:
        try:
            return [x[1] for x in self._internal.pop(self._normalize_key(key))]
        except KeyError:
            return []

    def add(self, key: KT, value: VT) -> None:
        key = self._normalize_key(key)
        self._internal.setdefault(key, []).append((key, self._normalize_value(value)))

    def extend(self, items: MultiMappingType) -> None:
        for k, v in items.items() if hasattr(items, "items") else items:
            self.add(k, v)

    def keys(self) -> typing.Iterable[NormKT]:
        for items in self._internal.values():
            if items:
                yield items[0][0]

    def values(self) -> typing.Iterable[NormVT]:
        for items in self._internal.values():
            for _, value in items:
                yield value

    def items(self) -> typing.Iterable[typing.Tuple[NormKT, NormVT]]:
        for items in self._internal.values():
            for k, v in items:
                yield k, v

    def setdefault(self, key: KT, value: VT) -> typing.List[NormVT]:
        return [
            x
            for _, x in self._internal.setdefault(
                self._normalize_key(key), [(key, self._normalize_value(value))]
            )
        ]

    def __contains__(self, item: KT) -> bool:
        return bool(self._internal.get(self._normalize_key(item), None))

    def __getitem__(self, item: KT) -> VT:
        try:
            return self._internal[self._normalize_key(item)][0][1]
        except (KeyError, IndexError):
            raise KeyError(item) from None

    def __setitem__(self, key: KT, value: VT):
        key = self._normalize_key(key)
        self._internal[key] = [(key, self._normalize_value(value))]

    def __delitem__(self, key: KT) -> None:
        self._internal.pop(self._normalize_key(key), None)

    def _normalize_key(self, key: KT) -> NormKT:
        return key

    def _normalize_value(self, value: VT) -> NormVT:
        return value


class Headers(
    MultiMapping[
        typing.Union[str, bytes],
        typing.Optional[typing.Union[str, bytes]],
        str,
        typing.Optional[str],
    ]
):
    def _normalize_key(self, key: KT) -> NormKT:
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        return key.lower()

    def _normalize_value(self, value: VT) -> NormVT:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return value

    def get_folded(self, key: str) -> str:
        if self._normalize_key(key) == "set-cookie":
            raise HTTPError("'Set-Cookie' header cannot be folded. Breaks semantics.")
        return "; ".join([x for x in self.get_all(key) if x is not None])

    def __repr__(self) -> str:
        # Smart repr that switches to list-of-tuple mode when
        # multiple values for one key are detected. Most of the
        # time it's easier to read the dictionary.
        if any(len(x) > 1 for x in self._internal.values()):
            internal_repr = repr([(k, v) for k, v in self.items()])
        else:
            # Note the unpacking within (k, v),
            internal_repr = repr({k: v for (k, v), in self._internal.values()})
        return f"<Headers {internal_repr}>"

    __str__ = __repr__


class Params(MultiMapping[str, ParamsValueType, str, ParamsValueType]):
    def __repr__(self) -> str:
        return f"<Params {[(k, v) for k, v in self.items()]!r}>"

    __str__ = __repr__


class Request:
    """Requests aren't painted async or sync, only their data is.
    By the time the request has been sent on the network and we'll
    get a response back the request will be attached to the response
    via 'SyncResponse.request'. At that point we can remove the 'data'
    parameter from the Request and only have the metadata left so
    users can't muck around with a spent Request body.

    We allow setting Request.target = '*' for both OPTIONS requests
    and for HTTP proxies providing the target in absolute form.
    If unset Request.target defaults to Request.url.path + ('?' + Request.url.params)?
    """

    def __init__(
        self, method: str, url: URLType, *, headers: HeadersType = None,
    ):
        self.method = method
        self.url = url

        self._headers = Headers(headers or ())
        self._target = None

    @property
    def url(self) -> URL:
        return self._url

    @url.setter
    def url(self, value: URLType) -> None:
        if not isinstance(value, URL):
            value = URL(value)
        self._url = value

    @property
    def headers(self) -> Headers:
        return self._headers

    @headers.setter
    def headers(self, value: HeadersType) -> None:
        self._headers = Headers(value)

    @property
    def target(self) -> str:
        if self._target is not None:
            return self._target
        return (
            f"{self.url.path or '/'}{'?' + self.url.params if self.url.params else ''}"
        )

    @target.setter
    def target(self, value: str) -> None:
        self._target = value

    def __repr__(self) -> str:
        return f"<Request [{self.method}]>"


class Response:
    def __init__(
        self,
        status_code: int,
        http_version: str,
        headers: HeadersType,
        request: typing.Optional[Request] = None,
    ):
        self.status_code = status_code
        self.http_version = http_version
        self.headers = headers
        self.request = request

        # Requests and aiohttp only give you 'Response' objects back in the history,
        # so you can't trace where each individual response was from or match it to a given request.
        # I think we're fine in doing that also? Requests mentions that only redirects end up
        # here, but maybe it'd also be nice to have 1XX responses and retried-responses end up here too.
        # The type-hint is 'Response' because users shouldn't depend on any Response body information
        # once they are here as they are already drained. Only header information should be used.
        self.history: typing.List[Response] = []

        self._headers: Headers
        self._encoding: typing.Optional[str] = None
        self._encoding_decoder: typing.Optional[codecs.IncrementalDecoder] = None

    def raise_for_status(self) -> None:
        """Raises an exception if the status_code is greater or equal to 400."""

    @property
    def content_type(self) -> str:
        """Gets the effective 'Content-Type' of the response either from headers
        or returns 'application/octet-stream' if no such header if found.
        """
        if "content-type" not in self.headers:
            return "application/octet-stream"
        content_type = "; ".join(self.headers.get_all("content-type"))
        mimetype = parse_mimetype(content_type)
        return str(mimetype)

    @property
    def content_length(self) -> typing.Optional[int]:
        if "content-length" in self.headers:
            values = self.headers.get_all("content-length")
            if len(set(values)) == 1 and values[0].isdigit():
                return int(values[0])
        return None

    @property
    def is_redirect(self) -> bool:
        """Gets whether the the response is a valid redirect.
        To be a redirect it must be a redirect status code and also
        have a valid 'Location' header.
        """
        return self.status_code in REDIRECT_STATUSES and "Location" in self.headers

    @property
    def headers(self) -> Headers:
        return self._headers

    @headers.setter
    def headers(self, value: HeadersType) -> None:
        if not isinstance(value, Headers):
            value = Headers(value)
        self._headers = value

    @property
    def encoding(self) -> typing.Optional[str]:
        """Returns the 'encoding' of the response body.
        - If encoding has been set manually, always use that value.
        - If the response has no body, return 'ascii'
        - If there is a 'charset=X' within the 'Content-Type' header
          and its an encoding that Python understands.
        - If the 'Content-Type' header starts with 'text/'
          try 'utf-8', then 'latin1' (never fails to decode)
        - If there is has been some body read it will be fed to chardet
          to determine the encoding.
        - If chardet isn't sure about the encoding, return 'None'.
        The '.stream_text()' method is smart will progressively read data from
        the response until chardet is confident enough in an encoding, then
        it will dump the decoded data afterwards and set an encoding internally.
        If our internal cache gets too big and chardet still isn't sure
        we will try utf-8 and then use latin1.
        If there is no response body (like Content-Length: 0, or a status
        code that shouldn't have a body) then this gives back 'ascii'
        as the body should be an empty byte string.
        """
        if self._encoding:
            return self._encoding
        if self.content_length == 0:
            self._encoding = "ascii"
        elif "content-type" in self.headers:
            content_type = self.headers.get_folded("content-type")
            mimetype = parse_mimetype(content_type)
            if "charset" in mimetype.parameters:
                encoding = is_known_encoding(mimetype.parameters["charset"])
                if encoding:
                    self._encoding = encoding
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        """Sets the encoding of the response body, overriding anything that
        would otherwise be detected via 'Content-Type' or chardet.
        """
        self._encoding = value

    def __repr__(self) -> str:
        return "<Response [%d]>" % self.status_code


class TLSVersion(enum.Enum):
    """Version specifier for TLS. Unless attempting to connect
    with only a single TLS version 'tls_max_version' should
    be 'MAXIMUM_SUPPORTED'
    """

    MINIMUM_SUPPORTED = "MINIMUM_SUPPORTED"
    TLSv1 = "TLSv1"
    TLSv1_1 = "TLSv1.1"
    TLSv1_2 = "TLSv1.2"
    TLSv1_3 = "TLSv1.3"
    MAXIMUM_SUPPORTED = "MAXIMUM_SUPPORTED"

    def resolve(self) -> "LiteralTLSVersionType":
        if self == TLSVersion.MINIMUM_SUPPORTED:
            return TLSVersion.TLSv1
        elif self == TLSVersion.MAXIMUM_SUPPORTED:
            return TLSVersion.TLSv1_3
        return self


# TLSVersion should be resolved to get rid of
# 'MINIMUM_SUPPORTED' and 'MAXIMUM_SUPPORTED'
# and replace with actual values for the TLS
# library being used.
LiteralTLSVersionType = typing.Union[
    typing.Literal[TLSVersion.TLSv1],
    typing.Literal[TLSVersion.TLSv1_1],
    typing.Literal[TLSVersion.TLSv1_2],
    typing.Literal[TLSVersion.TLSv1_3],
]


# All the TLS options
TLS_OP_NO_SSLv2 = getattr(ssl, "OP_NO_SSLv2", 0x01000000)
TLS_OP_NO_SSLv3 = getattr(ssl, "OP_NO_SSLv3", 0x02000000)
TLS_OP_NO_TLSv1 = getattr(ssl, "OP_NO_TLSv1", 0x04000000)
TLS_OP_NO_TLSv1_1 = getattr(ssl, "OP_NO_TLSv1_1", 0x10000000)
TLS_OP_NO_TLSv1_2 = getattr(ssl, "OP_NO_TLSv1_2", 0x08000000)
TLS_OP_NO_TLSv1_3 = getattr(ssl, "OP_NO_TLSv1_3", 0x20000000)
TLS_OP_NO_COMPRESSION = getattr(ssl, "OP_NO_COMPRESSION", 0x00020000)
TLS_OP_DEFAULTS = TLS_OP_NO_SSLv2 | TLS_OP_NO_SSLv3 | TLS_OP_NO_COMPRESSION
TLS_MIN_VERSION_OPTIONS: typing.Dict[TLSVersion, int] = {
    TLSVersion.MINIMUM_SUPPORTED: 0,
    TLSVersion.TLSv1: 0,
    TLSVersion.TLSv1_1: TLS_OP_NO_TLSv1,
    TLSVersion.TLSv1_2: (TLS_OP_NO_TLSv1 | TLS_OP_NO_TLSv1_1),
    TLSVersion.TLSv1_3: (TLS_OP_NO_TLSv1 | TLS_OP_NO_TLSv1_1 | TLS_OP_NO_TLSv1_2),
    TLSVersion.MAXIMUM_SUPPORTED: (
        TLS_OP_NO_TLSv1 | TLS_OP_NO_TLSv1_1 | TLS_OP_NO_TLSv1_2
    ),
}
TLS_MAX_VERSION_OPTIONS: typing.Dict[TLSVersion, int] = {
    TLSVersion.MINIMUM_SUPPORTED: (
        TLS_OP_NO_TLSv1_1 | TLS_OP_NO_TLSv1_2 | TLS_OP_NO_TLSv1_3
    ),
    TLSVersion.TLSv1: TLS_OP_NO_TLSv1_1 | TLS_OP_NO_TLSv1_2 | TLS_OP_NO_TLSv1_3,
    TLSVersion.TLSv1_1: TLS_OP_NO_TLSv1_2 | TLS_OP_NO_TLSv1_3,
    TLSVersion.TLSv1_2: TLS_OP_NO_TLSv1_3,
    TLSVersion.TLSv1_3: 0,
    TLSVersion.MAXIMUM_SUPPORTED: 0,
}


def create_ssl_context(
    ca_certs: typing.Optional[CACertsType],
    pinned_cert: typing.Optional[str],
    http_versions: typing.Sequence[str],
    tls_min_version: TLSVersion,
    tls_max_version: TLSVersion,
) -> ssl.SSLContext:

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)

    if ca_certs:
        if isinstance(ca_certs, bytes):
            ctx.load_verify_locations(cadata=ca_certs)
        elif os.path.isdir(ca_certs):
            ctx.load_verify_locations(capath=ca_certs)
        elif os.path.isfile(ca_certs):
            ctx.load_verify_locations(cafile=ca_certs)
        else:
            raise

    ctx.options |= (
        TLS_OP_DEFAULTS
        | TLS_MIN_VERSION_OPTIONS[tls_min_version]
        | TLS_MAX_VERSION_OPTIONS[tls_max_version]
    )

    alpn_protocols = [
        x for x in (http_version_to_alpn(ver) for ver in http_versions) if x
    ]
    if alpn_protocols:
        ctx.set_alpn_protocols(alpn_protocols)

    # If we're going to be checking a pinned cert fingerprint
    # then disable certificate verification. Will be
    # verified with verify_pinned_cert()
    if pinned_cert:
        ctx.verify_mode = ssl.CERT_NONE
        ctx.check_hostname = False
    else:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True

    return ctx


def http_version_to_alpn(http_version: str) -> typing.Optional[str]:
    """Given an HTTP version return the ALPN protocol identifier
    if one exists. If the HTTP version is valid but doesn't have
    a corresponding ALPN protocol identifier then return 'None'.
    """
    try:
        return {"HTTP/2": "h2", "HTTP/1.1": "http/1.1", "HTTP/1.0": None,}[http_version]
    except KeyError:
        raise ValueError(f"unknown http_version '{http_version}'") from None


def alpn_to_http_version(alpn: typing.Optional[str]) -> str:
    try:
        return {"h2": "HTTP/2", "http/1.1": "HTTP/1.1", None: "HTTP/1.1"}[alpn]
    except KeyError:
        raise ValueError(f"unknown alpn '{alpn}'") from None


def sslsocket_version_to_tls_version(
    version: typing.Optional[str],
) -> typing.Optional[TLSVersion]:
    if version is None:
        return None
    elif version == "TLSv1":
        return TLSVersion.TLSv1
    elif version == "TLSv1.1":
        return TLSVersion.TLSv1_1
    elif version == "TLSv1.2":
        return TLSVersion.TLSv1_2
    elif version == "TLSv1.3":
        return TLSVersion.TLSv1_3
    else:
        raise ValueError(f"unknown tls versiom '{version}'")


def verify_peercert_fingerprint(
    peercert: bytes, pinned_cert: typing.Tuple[str, str]
) -> None:
    """Checks the fingerprint of a certificate. Raises an exception
    if the pinned cert doesn't match the presented cert.
    """
    host, host_fingerprint = pinned_cert
    expected_fingerprint = binascii.unhexlify(host_fingerprint.replace(":", ""))
    algos: typing.Dict[int, typing.Any] = {
        16: hashlib.md5,
        20: hashlib.sha1,
        32: hashlib.sha256,
    }
    if len(expected_fingerprint) not in algos:
        raise ValueError(f"unknown hash algorithm for fingerprint '{pinned_cert[1]}'")

    actual_fingerprint = typing.cast(
        bytes, algos[len(expected_fingerprint)](peercert).digest()
    )

    if not hmac.compare_digest(expected_fingerprint, actual_fingerprint):
        raise CertificateFingerprintMismatch(
            f"'{host}' presented certificate with fingerprint "
            f"'{pretty_fingerprint(actual_fingerprint)}' but '{pretty_fingerprint(expected_fingerprint)}'"
            f"was expected via 'pinned_certs=...'."
        )


class Retry:
    """Both a configuration object for retries and the
    data-class that mutates as a Session attempts to
    complete a single request. A single 'Retry' object
    spans multiple
    """

    DEFAULT_RETRYABLE_METHODS = frozenset(
        ("HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE",)
    )
    DEFAULT_RETRY_AFTER_STATUS_CODES = frozenset((413, 429, 503))

    def __init__(
        self,
        # Number of total retries allowed.
        total_retries: typing.Optional[int] = None,
        *,
        # Number of retries allows for individual categories
        connect_retries: typing.Optional[int] = None,
        read_retries: typing.Optional[int] = None,
        response_retries: typing.Optional[int] = None,
        # Methods which are allowed to be retried (idempotent).
        retryable_methods: typing.Collection[str] = DEFAULT_RETRYABLE_METHODS,
        # Status codes that must be retried.
        retryable_status_codes: typing.Collection[int] = (),
        # Set a maximum value for 'Retry-After' where we send the request anyways.
        max_retry_after: typing.Optional[float] = 30.0,
        # Back-offs to not overwhelm a service experiencing
        # temporary errors and give time to recover.
        backoff_factor: float = 0.0,
        backoff_jitter: float = 0.0,
        max_backoff: typing.Optional[float] = 0.0,
        # Number of total times a request has been retried before
        # receiving a non-error response (less than 400) or received
        # a retryable error / timeout. This value gets reset to 0 by
        # .performed_http_redirect().
        _backoff_counter: int = 0,
    ):
        self.total_retries = total_retries
        self.connect_retries = connect_retries
        self.response_retries = response_retries
        self.retryable_methods = retryable_methods
        self.retryable_status_codes = retryable_status_codes
        self.max_retry_after = max_retry_after

        self.backoff_factor = backoff_factor
        self.backoff_jitter = backoff_jitter
        self.max_backoff = max_backoff

        self._backoff_counter = _backoff_counter

    def should_retry(
        self, request: Request, response: Response
    ) -> typing.Optional[Request]:
        """Returns whether the Request should be retried at all.
        Allows for rewriting the Request for sub-classes but currently
        just returns the Request that's been passed in.
        If the Request shouldn't be retried return 'None'.
        """
        if (
            request.method not in self.retryable_methods
            or response.status_code not in self.retryable_status_codes
        ):
            return None
        return request

    def delay_before_next_request(
        self, response: typing.Optional[Response] = None
    ) -> float:
        """Returns the delay in seconds between issuing the next request.
        This interface combines backoff and 'Retry-After' headers into one.
        """
        delay = self._delay_backoff()
        if response is not None:
            delay = max(delay, self._delay_retry_after(response))
        return delay

    def reset_backoff_counter(self) -> None:
        """Callback that signals to the 'Retry' instance that an HTTP
        redirect was performed and the '_backoff_counter' should
        be reset to 0 so that back-offs don't continue to grow
        after a service successfully processes our request.
        This callback shouldn't be called when a redirect is returned
        back to the caller, because it's basically a no-op in that case.
        """
        self._backoff_counter = 0

    def increment(
        self,
        *,
        connect: bool = False,
        read: bool = False,
        response: typing.Optional[Response] = None,
        error: typing.Optional[Exception] = None,
    ) -> None:
        """Increments the Retry instance down by the given values.
        """

    def copy(self) -> "Retry":
        """Creates a new instance of the current 'Retry' object. This is used
        by the 'Session' object to not modify the Session object's instance
        used for configuration.
        """

    def _delay_backoff(self) -> float:
        max_backoff = none_is_inf(self.max_backoff)
        if max_backoff <= 0.0:
            return 0.0

        # Apply jittering to not hammer a service on regular intervals
        # when errors start occurring. Amazon says that backoff_jitter=1.0
        # is optimal for this case.
        jitter_factor = 1.0
        if self.backoff_jitter > 0.0:
            jitter_factor = (1.0 - self.backoff_jitter) + secrets.randbelow(
                self.backoff_jitter
            )

        backoff: float = (
            self.backoff_factor * (2 ** (self._backoff_counter - 1)) * jitter_factor
        )
        return min(max_backoff, backoff)

    def _delay_retry_after(self, response: Response) -> float:
        retry_after = response.headers.get("Retry-After", "0")
        return float(retry_after or 0)
