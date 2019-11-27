import json
import typing

HeadersType = typing.Union[
    typing.Mapping[str, str],
    typing.Mapping[bytes, bytes],
    typing.Iterable[typing.Tuple[str, str]],
    typing.Iterable[typing.Tuple[bytes, bytes]],
]
Request: typing.Any  # TODO: Replace with the actual Request type.

CHUNK_SIZE = 16384
REDIRECT_STATUSES = {
    301,  # Moved Permanently
    302,  # Found
    303,  # See Other
    307,  # Temporary Redirect
    308,  # Permanent Redirect
}

class BaseResponse:
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
    def raise_for_status(self) -> None:
        """Raises an exception if the status_code is greater or equal to 400."""
    @property
    def content_type(self) -> str:
        """Gets the effective 'Content-Type' of the response either from headers
        or returns 'application/octet-stream' if no such header if found.
        """
    @property
    def is_redirect(self) -> bool:
        """Gets whether the the response is a valid redirect.
        To be a redirect it must be a redirect status code and also
        have a valid 'Location' header.
        """
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
    @property
    def history(self) -> typing.Sequence["BaseResponse"]:
        """Gets the history of how the first request eventually turned into this singular response.

        Requests and aiohttp only gives you 'Response' objects back in the history,
        so you can't trace where each individual response was from or match it to a given request.
        I think we're fine in doing that also? Requests mentions that only redirects end up
        here, but maybe it'd also be nice to have 1XX responses and retried-responses end up here too.

        The type-hint is 'BaseResponse' because users shouldn't depend on any Response body information
        once they are here as they are already drained. Only header information should be used.
        """
        ...
    def __repr__(self) -> str:
        return "<Response [%d]>" % self.status_code

class SyncResponse(BaseResponse):
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

        This function will also have to deal with BaseResponse.encoding returning
        'None' because not all data will be read from the response necessarily
        meaning we'll have to use chardets incremental support.
        """
    def data(self) -> bytes:
        """Basically calls b''.join(self.stream()) and hands it to you"""
    def text(self) -> str:
        """Same as above except ''.join(self.stream_text())"""
    @typing.overload
    def as_file(self, mode: typing.Literal["r"] = "rb") -> typing.TextIO: ...
    @typing.overload
    def as_file(self, mode: typing.Literal["rb"] = "rb") -> typing.BinaryIO: ...
    def as_file(self, mode="r") -> typing.Union[typing.BinaryIO, typing.TextIO]:
        """Creates a file-like object that can be used within things like csv.DictReader(),
        data-frames, and other interfaces expecting a file-like interface.

        I don't know what this would look like on the async-side. For now I have omitted it.
        Looking at what trio exposes as an interface is probably a good place to start.
        """
    def json(
        self, loads: typing.Callable[[str], typing.Any] = json.loads
    ) -> typing.Any:
        """Attempts to decode self.text() into JSON, optionally with a custom JSON loader."""
    def close(self) -> None:
        """Flushes the response body and puts the connection back into the pool"""
    def __enter__(self) -> "SyncResponse": ...
    def __exit__(self, *_: typing.Any) -> None:
        """Automatically closes the response for you once the context manager is exited"""

class AsyncResponse(BaseResponse):
    async def stream(self, chunk_size: int = None) -> typing.AsyncIterator[bytes]: ...
    async def stream_text(
        self, chunk_size: int = None, encoding: typing.Optional[str] = None
    ) -> typing.AsyncIterator[str]: ...
    async def data(self) -> bytes: ...
    async def text(self) -> str: ...
    async def json(
        self, loads: typing.Callable[[str], typing.Any] = json.loads
    ) -> typing.Any: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> "AsyncResponse": ...
    async def __aexit__(self, *_: typing.Any) -> None: ...
