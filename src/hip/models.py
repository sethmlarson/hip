import typing
import pathlib
import enum
import secrets
import json


PathType = typing.Union[str, pathlib.Path]
CACertsType = typing.Union[PathType, bytes]
PinnedCertsType = typing.Mapping[str, str]
TimeoutType = typing.Any
RetriesType = typing.Union[int, "Retry"]
RedirectsType = typing.Union[bool, int]
HeadersType = typing.Union[
    typing.Mapping[str, str],
    typing.Mapping[bytes, bytes],
    typing.Iterable[typing.Tuple[str, str]],
    typing.Iterable[typing.Tuple[bytes, bytes]],
    "Headers",
]
URLType = typing.Union[str, "URL"]
ProxiesType = typing.Mapping[str, URLType]
CookiesType = typing.Mapping[str, str]

CHUNK_SIZE = 16384
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
ParamsValueType = typing.Union[str, _ParamNoValue]
ParamsType = typing.Union[
    typing.Sequence[typing.Tuple[str, ParamsValueType]],
    typing.Mapping[str, typing.Optional[ParamsValueType]],
]


class Origin:
    def __init__(self, scheme: str, host: str, port: int):
        self.scheme = scheme
        self.host = host
        self.port = port

    def __eq__(self, other: "Origin") -> bool:
        if not isinstance(other, Origin):
            return NotImplemented
        return (
            self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __ne__(self, other: "Origin") -> bool:
        if not isinstance(other, Origin):
            return NotImplemented
        return not self == other


class URL:
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
        return Origin(self.scheme, self.host, self.port)

    def join(self, url: URLType) -> "URL":
        ...


KT = typing.TypeVar("KT")
VT = typing.TypeVar("VT")
MultiMappingType = typing.Union[
    typing.Mapping[KT, VT], typing.Sequence[typing.Tuple[KT, VT]]
]


class MultiMapping(typing.Generic[KT, VT]):
    def __init__(self, values: MultiMappingType = ()):
        self._internal: typing.Dict[KT, typing.List[typing.Tuple[KT, VT]]] = {}
        self.extend(values)

    def get_one(
        self, key: KT, default: typing.Optional[VT] = None
    ) -> typing.Optional[VT]:
        try:
            return self._internal[self._normalize(key)][0][1]
        except (KeyError, IndexError):
            return default

    get = get_one

    def get_all(self, key: KT) -> typing.List[VT]:
        try:
            return [x[1] for x in self._internal[self._normalize(key)]]
        except KeyError:
            return []

    def pop_one(
        self, key: KT, default: typing.Optional[VT] = None
    ) -> typing.Optional[VT]:
        try:
            items = self._internal[self._normalize(key)]
            return items.pop(0)[1]
        except (KeyError, IndexError):
            return default

    pop = pop_one

    def pop_all(self, key: KT) -> typing.List[VT]:
        try:
            return [x[1] for x in self._internal.pop(self._normalize(key))]
        except KeyError:
            return []

    def add(self, key: KT, value: VT) -> None:
        self._internal.setdefault(self._normalize(key), []).append((key, value))

    def extend(self, items: MultiMappingType) -> None:
        for k, v in items.items() if hasattr(items, "items") else items:
            self.add(k, v)

    def keys(self) -> typing.Iterable[KT]:
        for items in self._internal.values():
            if items:
                yield items[0][0]

    def values(self) -> typing.Iterable[VT]:
        for items in self._internal.values():
            for _, value in items:
                yield value

    def items(self) -> typing.Iterable[typing.Tuple[KT, VT]]:
        for items in self._internal.values():
            for k, v in items:
                yield k, v

    def __getitem__(self, item: KT) -> VT:
        try:
            return self._internal[self._normalize(item)][0][1]
        except (KeyError, IndexError):
            raise KeyError(item) from None

    def __setitem__(self, key: KT, value: VT):
        self._internal[self._normalize(key)] = [(key, value)]

    def __delitem__(self, key: KT) -> None:
        self._internal.pop(self._normalize(key), None)

    def _normalize(self, key: KT) -> KT:
        return key


class Headers(MultiMapping[str, typing.Optional[str]]):
    def _normalize(self, key: KT) -> KT:
        return key.lower()

    def __repr__(self) -> str:
        return f"<Headers {[(k, v) for k, v in self.items()]!r}>"

    __str__ = __repr__


class Params(MultiMapping[str, ParamsValueType]):
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

    def raise_for_status(self) -> None:
        """Raises an exception if the status_code is greater or equal to 400."""

    @property
    def content_type(self) -> str:
        """Gets the effective 'Content-Type' of the response either from headers
        or returns 'application/octet-stream' if no such header if found.
        """
        if "Content-Type" not in self.headers:
            return "application/json"
        content_type = self.headers.get_folded("Content-Type")
        return content_type.split(";", 1).strip()

    @property
    def is_redirect(self) -> bool:
        """Gets whether the the response is a valid redirect.
        To be a redirect it must be a redirect status code and also
        have a valid 'Location' header.
        """
        return self.status_code in REDIRECT_STATUSES and "Location" in self.headers

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

    @encoding.setter
    def encoding(self, value: str) -> None:
        """Sets the encoding of the response body, overriding anything that
        would otherwise be detected via 'Content-Type' or chardet.
        """

    def __repr__(self) -> str:
        return "<Response [%d]>" % self.status_code


class SyncResponse(Response):
    def stream(self, chunk_size: typing.Optional[int] = None) -> typing.Iterator[bytes]:
        """Streams the response body as an iterator of bytes.
        Optionally set the chunk size, if chunk size is set
        then you are guaranteed to get chunks exactly equal to the
        size given *except* for the last chunk of data and for
        the case where the response body is empty. If the
        response body is empty the iterator will immediately
        raise 'StopIteration'.
        """

    def stream_text(
        self, chunk_size: typing.Optional[int] = None
    ) -> typing.Iterator[str]:
        """Same as above except decodes the bytes into str while iterating.
        Critical point to note is that 'chunk_size' corresponds to the
        length of the decoded string, not the length of the bytes being read.
        We'll have to deal with reading partial multi-byte characters from the wire
        and somehow making the best of it.
        This function will also have to deal with Response.encoding returning
        'None' because not all data will be read from the response necessarily
        meaning we'll have to use chardets incremental support.
        """

    def data(self) -> bytes:
        """Basically calls b''.join(self.stream()) and hands it to you"""
        if not hasattr(self, "_content"):
            self._content = []
            for chunk in self.stream():
                self._content.append(chunk)
        return b"".join(self._content)

    def text(self) -> str:
        """Same as above except ''.join(self.stream_text())"""
        return self.data().decode(self.encoding)

    @typing.overload
    def as_file(self, mode: typing.Literal["r"]) -> typing.TextIO:
        ...

    @typing.overload
    def as_file(self, mode: typing.Literal["rb"]) -> typing.BinaryIO:
        ...

    def as_file(self, mode: str = "r") -> typing.Union[typing.TextIO, typing.BinaryIO]:
        """Creates a file-like object that can be used within things like csv.DictReader(),
        data-frames, and other interfaces expecting a file-like interface.
        I don't know what this would look like on the async-side. For now I have omitted it.
        Looking at what trio exposes as an interface is probably a good place to start.
        """

    def json(
        self, loads: typing.Callable[[str], typing.Any] = json.loads
    ) -> typing.Any:
        """Attempts to decode self.text() into JSON, optionally with a custom JSON loader."""
        return loads(self.text())

    def close(self) -> None:
        """Flushes the response body and puts the connection back into the pool"""

    def __enter__(self) -> "SyncResponse":
        ...

    def __exit__(self, *_: typing.Any) -> None:
        """Automatically closes the response for you once the context manager is exited"""
        self.close()


class AsyncResponse(Response):
    def stream(
        self, chunk_size: typing.Optional[int] = None
    ) -> typing.AsyncIterator[bytes]:
        ...

    def stream_text(
        self,
        chunk_size: typing.Optional[int] = None,
        encoding: typing.Optional[str] = None,
    ) -> typing.AsyncIterator[str]:
        ...

    async def data(self) -> bytes:
        if not hasattr(self, "_content"):
            self._content = []
            async for chunk in self.stream():
                self._content.append(chunk)
        return b"".join(self._content)

    async def text(self) -> str:
        return (await self.data()).decode(self.encoding)

    async def json(
        self, loads: typing.Callable[[str], typing.Any] = json.loads
    ) -> typing.Any:
        return loads((await self.text()))

    async def close(self) -> None:
        ...

    async def __aenter__(self) -> "AsyncResponse":
        ...

    async def __aexit__(self, *_: typing.Any) -> None:
        await self.close()


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
        redirect was performed and the '_back_to_back_errors' counter
        should be reset to 0 so that back-offs don't continue to grow
        after a service successfully processes our request.
        This callback shouldn't be called when a redirect is returned
        by to the caller, because it's basically a no-op in that case.
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
        if self.max_backoff <= 0.0:
            return 0.0

        # Apply jittering to not hammer a service on regular intervals
        # when errors start occurring. Amazon says that backoff_jitter=1.0
        # is optimal for this case.
        jitter_factor = 1.0
        if self.backoff_jitter > 0.0:
            jitter_factor = (1.0 - self.backoff_jitter) + secrets.randbelow(
                self.backoff_jitter
            )

        backoff = (
            self.backoff_factor * (2 ** (self._backoff_counter - 1)) * jitter_factor
        )
        return min(self.max_backoff, backoff)

    def _delay_retry_after(self, response: Response) -> float:
        retry_after = response.headers.get("Retry-After", "0")
        return float(retry_after)
