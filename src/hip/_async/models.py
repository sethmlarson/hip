import os
import binascii
import typing
import json
import chardet
from hip.models import HeadersType, Request, Headers, Response as BaseResponse
from hip.utils import INT_TO_URLENC, encoding_detector


AuthType = typing.Union[
    typing.Tuple[typing.Union[str, bytes], typing.Union[str, bytes]],
    typing.Callable[[Request], Request],
    # unasync needs to change typing.Awaitable[X] -> X
    typing.Callable[[Request], typing.Awaitable[Request]],
]
CookiesType = typing.Union[
    typing.Mapping[str, str], "Cookies",
]
DataType = typing.Union[
    typing.Union[str, bytes],
    typing.BinaryIO,
    typing.TextIO,
    "RequestData",
    typing.Iterable[typing.Union[str, bytes]],
    # This needs to get unasync-ed into 'typing.Iterable[typing.Union[str, bytes]]'
    typing.AsyncIterable[typing.Union[str, bytes]],
]
JSONType = typing.Union[
    typing.Mapping[typing.Any, typing.Any],
    typing.Sequence[typing.Any],
    int,
    bool,
    str,
    float,
    None,
]


def detect_is_async() -> typing.Union[typing.Literal[True], typing.Literal[False]]:
    """Tests if we're in the async part of the code or not"""

    async def f():
        """Unasync transforms async functions in sync functions"""
        return None

    obj = f()
    if obj is None:
        return typing.cast(typing.Literal[False], False)
    else:
        obj.close()  # prevent un-awaited coroutine warning
        return typing.cast(typing.Literal[True], True)


IS_ASYNC = detect_is_async()


class Response(BaseResponse):
    def __init__(
        self,
        status_code: int,
        http_version: str,
        headers: HeadersType,
        request: typing.Optional[Request] = None,
        raw_data: typing.Optional[typing.AsyncIterator[bytes]] = None,
    ):
        super().__init__(status_code, http_version, headers, request=request)
        self._raw_data = raw_data
        self._content: typing.List[bytes]

    def stream(
        self, chunk_size: typing.Optional[int] = None
    ) -> typing.AsyncIterator[bytes]:
        """Streams the response body as an iterator of bytes.
        Optionally set the chunk size, if chunk size is set
        then you are guaranteed to get chunks exactly equal to the
        size given *except* for the last chunk of data and for
        the case where the response body is empty. If the
        response body is empty the iterator will immediately
        raise 'StopIteration'.
        """

        async def stream_gen() -> typing.AsyncIterable[bytes]:
            nonlocal self
            encoding = self.encoding

            # If our encoding isn't known from headers
            # then we need to fire up chardets decoder.
            detector: typing.Optional[chardet.UniversalDetector]
            if encoding is None:
                detector = encoding_detector()
            else:
                detector = None

            received_data = 0
            async for chunk in self._raw_data:
                # Feed data into detector until we get a result.
                received_data += len(chunk)
                if detector:
                    detector.feed(chunk)
                    if detector.result and (
                        detector.result["encoding"] or received_data > 4096
                    ):
                        self._encoding = detector.result["encoding"] or "utf-8"
                        detector = None

                yield chunk

            # If we didn't receive any data then our encoding is 'ascii'
            # and if we did receive data and are still stumped use 'utf-8'.
            if self._encoding is None:
                if received_data == 0:
                    self._encoding = "ascii"
                else:
                    self._encoding = "utf-8"

        return stream_gen().__aiter__()

    def stream_text(
        self, chunk_size: typing.Optional[int] = None,
    ) -> typing.AsyncIterator[str]:
        """Same as above except decodes the bytes into str while iterating.
        Critical point to note is that 'chunk_size' corresponds to the
        length of the decoded string, not the length of the bytes being read.
        We'll have to deal with reading partial multi-byte characters from the wire
        and somehow making the best of it.
        This function will also have to deal with Response.encoding returning
        'None' because not all data will be read from the response necessarily
        meaning we'll have to use chardets incremental support.
        """
        buffer = bytearray()
        buffer_flushed = False

        async def stream_gen() -> typing.AsyncIterable[str]:
            nonlocal buffer, buffer_flushed
            async for chunk in self.stream():
                if self._encoding is None:
                    buffer += chunk
                else:
                    if not buffer_flushed:
                        buffer_flushed = True
                        if len(buffer):
                            yield bytes(buffer).decode(self._encoding)
                    yield chunk.decode(self._encoding)

            if not buffer_flushed:
                yield bytes(buffer).decode(self._encoding)

        return stream_gen().__aiter__()

    async def data(self) -> bytes:
        """Basically calls b''.join(self.stream()) and hands it to you"""
        if not hasattr(self, "_content"):
            self._content = []
            async for chunk in self.stream():
                self._content.append(chunk)
        return b"".join(self._content)

    async def text(self) -> str:
        """Same as above except ''.join(self.stream_text())"""
        return (await self.data()).decode(self.encoding)

    async def json(
        self, loads: typing.Callable[[str], typing.Any] = json.loads
    ) -> typing.Any:
        """Attempts to decode self.text() into JSON, optionally with a custom JSON loader."""
        return loads((await self.text()))

    async def close(self) -> None:
        """Flushes the response body and puts the connection back into the pool"""

    async def __aenter__(self) -> "AsyncResponse":
        return self

    async def __aexit__(self, *_: typing.Any) -> None:
        """Automatically closes the response for you once the context manager is exited"""
        await self.close()


class RequestData:
    """Represents a synchronous request data object. Basically a wrapper around whatever
    a user passes in via 'data' / 'json', etc parameters. We can take bytes /
    strings, iterators of bytes or strings, and files. We can also sub-class / implement
    a file-like interface for things like multipart-formdata so it's possible to
    rewind (unlike the current urllib3 interface).
    Maybe in the future we can expose details about when an object can be sent via
    'socket.sendfile()', etc. This would have to be communicated somehow to the
    low-level backend streams.
    When we're handed a file-like object we should take down the starting point
    in the file via .tell() so we can rewind and put the pointer back after
    the seek() call in '.content_length()'
    Ref: https://github.com/python-trio/urllib3/issues/135
    """

    async def content_length(self) -> typing.Optional[int]:
        """We can get a proper content-length for bytes, strings, file-like objects
        that are opened in binary mode (is that detectable somehow?). If we hand
        back 'None' from this property it means that the request should use
        'Transfer-Encoding: chunked'
        """
        raise NotImplementedError()

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        """Factory object for creating an iterable over the wrapped object.
        If the internal data is not rewindable and this function is called
        then a 'hip.UnrewindableBodyError' is raised.
        """
        raise NotImplementedError()

    @property
    def content_type(self) -> typing.Optional[str]:
        raise NotImplementedError()


class NoData(RequestData):
    async def content_length(self) -> typing.Optional[int]:
        return 0

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        return typing.cast(typing.AsyncIterator[bytes], self)

    async def __anext__(self) -> None:
        raise StopAsyncIteration()

    @property
    def content_type(self) -> typing.Optional[str]:
        return None


class Bytes(RequestData):
    """Class representing the simplest data-type, just bytes."""

    def __init__(self, data: bytes):
        self._data = data

    async def content_length(self) -> typing.Optional[int]:
        return len(self._data)

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        async def _inner() -> typing.AsyncIterable[bytes]:
            yield self._data

        return _inner().__aiter__()

    @property
    def content_type(self) -> str:
        return "application/octet-stream"


class File(RequestData):
    """Class representing a file-like interface"""


def compact_json_dumps(obj: JSONType) -> str:
    """Function that doesn't add extra whitespace when encoding JSON"""
    return json.dumps(obj, separators=(",", ":"))


class JSON(RequestData):
    def __init__(
        self,
        json: JSONType,
        json_dumps: typing.Callable[[JSONType], str] = compact_json_dumps,
    ):
        self._json = json
        self._json_dumps = json_dumps
        self._data: typing.Optional[bytes] = None

    async def content_length(self) -> typing.Optional[int]:
        return len(self._encode_json())

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        async def _inner() -> typing.AsyncIterable[bytes]:
            yield self._encode_json()

        return _inner().__aiter__()

    @property
    def content_type(self) -> str:
        return "application/json"

    def _encode_json(self) -> bytes:
        if self._data is None:
            self._data = self._json_dumps(self._json).encode("utf-8")
        return self._data


StrOrInt = typing.Union[str, int]
FormType = typing.Union[
    typing.Sequence[typing.Tuple[str, StrOrInt]],
    typing.Mapping[str, typing.Union[StrOrInt, typing.Sequence[StrOrInt]]],
]


class URLEncodedForm(RequestData):
    """Implements application/x-www-form-urlencoded as a RequestData object"""

    def __init__(self, form: FormType):
        self._form = form
        self._data = None

    @property
    def content_type(self) -> str:
        return "application/x-www-form-urlencoded"

    async def content_length(self) -> int:
        return len(self._encode_form())

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        async def _inner() -> typing.AsyncIterable[bytes]:
            yield self._encode_form()

        return _inner().__aiter__()

    def _encode_form(self) -> bytes:
        if self._data is None:

            def serialize(x: str) -> bytes:
                return b"".join([INT_TO_URLENC[byte] for byte in x.encode("utf-8")])

            output: typing.List[bytes] = []
            for k, vs in (
                self._form.items() if hasattr(self._form, "items") else self._form
            ):
                if isinstance(vs, str) or not hasattr(vs, "__iter__"):
                    vs = (vs,)
                for v in vs:
                    output.append(serialize(k) + b"=" + serialize(v))

            self._data = b"&".join(output)

        return self._data


class MultipartFormField(RequestData):
    def __init__(
        self,
        name: str,
        data: typing.Optional[typing.Union[bytes, str, typing.BinaryIO]] = None,
        filename: typing.Optional[str] = None,
        headers: typing.Optional[HeadersType] = None,
    ):
        self._headers: Headers  # NOTE: Only a type annotation here.
        self.name = name
        self.data = data
        self.filename = filename
        self.headers = headers

    @property
    def headers(self) -> Headers:
        return self._headers

    @headers.setter
    def headers(self, value: typing.Optional[HeadersType]) -> None:
        if not isinstance(value, Headers):
            value = Headers(value or ())
        self._headers = value

    async def content_length(self) -> int:
        ...

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        ...

    @property
    def content_type(self) -> str:
        return self.headers.get_one("content-type", "application/octet-stream")


class MultipartForm(RequestData):
    """Implements multipart/form-data as a RequestData object"""

    def __init__(self, form):
        self._form = form
        self._boundary: typing.Optional[str] = None

    def add_field(
        self,
        name: str,
        *,
        data: typing.Optional[typing.Union[bytes, str, typing.BinaryIO]] = None,
        filename: typing.Optional[str] = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[HeadersType] = None,
    ) -> None:
        ...

    async def content_length(self) -> typing.Optional[int]:
        field_size = 0
        number_of_fields = 0
        for field in self._iter_fields():
            number_of_fields += 1
            field_size += await field.content_length()
        return (6 + len(self.boundary)) * (number_of_fields + 1)

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        boundary_bytes = self.boundary.encode()
        for field in self._iter_fields():
            yield b"--%b\r\n%b" % (boundary_bytes, field.render_headers())
            async for chunk in (await field.data_chunks()):
                yield chunk
        yield b"--%b--\r\n" % boundary_bytes

    @property
    def content_type(self) -> str:
        return f"multipart/form-data; boundary={self.boundary}"

    @property
    def boundary(self) -> str:
        if self._boundary is None:
            self._boundary = binascii.hexlify(os.urandom(16)).decode()
        return self._boundary

    def _iter_fields(self) -> typing.Iterable[MultipartFormField]:
        ...
