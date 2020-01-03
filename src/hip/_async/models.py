import io
import os
import binascii
import typing
import json
import chardet
import filetype
import mimetypes
from hip.models import HeadersType, Request, Headers, Response as BaseResponse
from hip.decoders import get_content_decoder
from hip.utils import INT_TO_URLENC, encoding_detector, TextChunker, BytesChunker
from hip import utils
from .utils import sync_or_async, IS_ASYNC

AsyncAuthType = typing.Callable[[Request], typing.Awaitable[Request]]
SyncAuthType = typing.Callable[[Request], Request]

AuthType = typing.Union[
    typing.Tuple[typing.Union[str, bytes], typing.Union[str, bytes]],
    typing.Callable[[Request], Request],
    AsyncAuthType,
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
        self._decoder = get_content_decoder(
            self.headers.get("Content-Encoding", "identity")
        )

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

            async def decode_raw_data() -> typing.AsyncIterable[bytes]:
                """Decodes the raw data if an encoding has been applied."""
                decoder = get_content_decoder(
                    self.headers.get("Content-Encoding", "identity")
                )
                async for chunk in self._raw_data:
                    chunk = decoder.decompress(chunk)
                    if chunk:
                        yield chunk
                chunk = decoder.flush()
                if chunk:
                    yield chunk

            chunker = BytesChunker(chunk_size)
            received_data = 0
            async for chunk in decode_raw_data():
                # Feed data into detector until we get a result.
                received_data += len(chunk)
                if detector:
                    detector.feed(chunk)
                    if detector.result and (
                        detector.result["encoding"] or received_data > 4096
                    ):
                        self._encoding = detector.result["encoding"] or "utf-8"
                        detector = None

                for data in chunker.feed(chunk):
                    yield data

            for data in chunker.flush():
                yield data

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
        chunker: typing.Optional[TextChunker] = None

        async def stream_gen() -> typing.AsyncIterable[str]:
            nonlocal buffer, buffer_flushed, chunker
            async for chunk in self.stream():
                if self._encoding is None:
                    buffer += chunk
                else:
                    if chunker is None:
                        chunker = TextChunker(
                            encoding=self._encoding, chunk_size=chunk_size
                        )
                    if not buffer_flushed:
                        buffer_flushed = True
                        if len(buffer):
                            for data in chunker.feed(bytes(buffer)):
                                yield data
                    for data in chunker.feed(chunk):
                        yield data

            if chunker is None:
                chunker = TextChunker(encoding=self._encoding, chunk_size=chunk_size)

            if not buffer_flushed and len(buffer):
                for data in chunker.feed(bytes(buffer)):
                    yield data

            for data in chunker.flush():
                yield data

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

    async def json(self) -> typing.Any:
        """Attempts to decode self.text() into JSON."""
        return json.loads((await self.text()))

    async def close(self) -> None:
        """Flushes the response body which should
        release the connection back into the pool.
        """
        async for _ in self._raw_data:
            pass

    async def __aenter__(self) -> "Response":
        return self

    async def __aexit__(self, *_: typing.Any) -> None:
        """Automatically closes the response for you once the context manager is exited"""
        await self.close()

    @typing.overload
    def as_file(self, mode: typing.Literal["r"]) -> io.TextIOBase:
        ...

    @typing.overload
    def as_file(self, mode: typing.Literal["rb"]) -> io.IOBase:
        ...

    def as_file(self, mode: str = "r") -> typing.Union[io.TextIOBase, io.IOBase]:
        """Creates a file-like object that can be used within things like csv.DictReader(),
        data-frames, and other interfaces expecting a file-like interface.
        I don't know what this would look like on the async-side. Looking at what trio
        exposes as an interface is probably a good place to start.
        """


class _ResponseTextIO(io.TextIOBase):
    def __init__(self, response: Response) -> None:
        self._response = response
        self._closed = False

    def read(self, n: typing.Optional[int] = None) -> str:
        pass

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._response.close()
            self._response = None

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "_ResponseTextIO":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _ResponseBinaryIO(io.IOBase):
    def __init__(self, response: Response) -> None:
        self._response = response
        self._closed = False

    def read(self, n: typing.Optional[int] = None) -> str:
        pass

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._response.close()
            self._response = None

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "_ResponseBinaryIO":
        return self

    def __exit__(self, *_) -> None:
        self.close()


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

    async def content_type(self) -> typing.Optional[str]:
        raise NotImplementedError()


class NoData(RequestData):
    async def content_length(self) -> typing.Optional[int]:
        return 0

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        return typing.cast(typing.AsyncIterator[bytes], self)

    async def __anext__(self) -> None:
        raise StopAsyncIteration()

    async def content_type(self) -> typing.Optional[str]:
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

    async def content_type(self) -> str:
        return "application/octet-stream"


class File(RequestData):
    """Class representing a file-like interface"""

    def __init__(self, fp: io.IOBase):
        self._fp = fp
        self._content_type: typing.Optional[str]
        # Initial location of the file pointer before data
        # transmission starts.
        self._fp_begin: typing.Optional[int] = None
        self._fp_end: typing.Optional[int] = None

    async def content_type(self) -> typing.Optional[str]:
        if not hasattr(self._fp, "seek"):
            return None
        await self._get_fp_begin()
        if not hasattr(self, "_content_type"):
            data = await self._fp_read(utils.CHUNK_SIZE)
            content_type = filetype.guess_mime(data)

            # Couldn't guess by the contents of the file, so
            # we try the name of the file as a last-ditch effort.
            if content_type is None and hasattr(self._fp, "name"):
                try:
                    filename = os.path.basename(str(self._fp.name))
                    content_type, _ = mimetypes.guess_type(filename, strict=False)
                except Exception:
                    pass
            self._content_type = content_type
        return self._content_type

    async def content_length(self) -> typing.Optional[int]:
        return (await self._get_fp_end()) - (await self._get_fp_begin())

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        async def _inner() -> typing.AsyncIterable[bytes]:
            data = await self._fp_read(utils.CHUNK_SIZE)
            while data:
                yield data
                data = await self._fp_read(utils.CHUNK_SIZE)

        self._fp.seek(await self._get_fp_begin(), 0)
        return _inner().__aiter__()

    async def _get_fp_begin(self) -> int:
        if self._fp_begin is None:
            self._fp_begin = self._fp.tell()
        return self._fp_begin

    async def _get_fp_end(self) -> int:
        if self._fp_end is None:
            fp_begin = await self._get_fp_begin()
            self._fp.seek(0, 2)
            self._fp_end = self._fp.tell()
            self._fp.seek(fp_begin, 0)
        return self._fp_end

    async def _fp_tell(self) -> int:
        return await sync_or_async(self._fp.tell)

    async def _fp_seek(self, offset: int, whence: int) -> None:
        await sync_or_async(self._fp.seek, offset, whence)

    async def _fp_read(self, nbytes: int) -> bytes:
        if IS_ASYNC:
            read = getattr(self._fp, "aread", self._fp.read)
        else:
            read = self._fp.read
        return await sync_or_async(read, nbytes)


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
    """Essentially a wrapper for a 'RequestData' object with
    a name, filename, and headers.
    """

    def __init__(
        self,
        name: str,
        *,
        data: RequestData,
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

    async def content_length(self) -> typing.Optional[int]:
        data_length = await self.data.content_length()
        if data_length is None:
            return None
        return len(self.render_headers()) + data_length

    async def data_chunks(self) -> typing.AsyncIterator[bytes]:
        return await self.data.data_chunks()

    @property
    def content_type(self) -> str:
        return self.headers.get_one("content-type", self.data.content_type)

    def render_headers(self) -> bytes:
        """Renders the headers for the Multipart field."""
        lines = []

        # Render these headers before any others as they're defined in the standard.
        priority_headers = ("content-disposition", "content-type")
        for name in priority_headers:
            value = self.headers.get(name, None)
            if value is not None:
                lines.append(b"%b: %b" % (name.encode(), value.encode()))

        for name, value in self.headers.items():
            name = name.lower()
            if value is not None and name not in priority_headers:
                lines.append(b"%b: %b" % (name.encode(), value.encode()))

        lines.append(b"\r\n")
        return b"\r\n".join(lines)


class MultipartForm(RequestData):
    """Implements multipart/form-data as a RequestData object"""

    def __init__(self, fields=None):
        self._fields: typing.List[MultipartFormField] = fields or []
        self._boundary: typing.Optional[str] = None

    def add_field(
        self,
        name: str,
        data: DataType,
        *,
        filename: typing.Optional[str] = None,
        headers: typing.Optional[HeadersType] = None,
    ) -> MultipartFormField:
        """Adds a field to the multipart form"""
        field = MultipartFormField(
            name=name, data=data, filename=filename, headers=headers
        )
        self._fields.append(field)
        return field

    async def content_length(self) -> typing.Optional[int]:
        """Needs to check all fields to see that they have a defined
        length (non-iterable). If any field doesn't have a defined length
        then we must use the chunked transfer-encoding for the entire message.
        """
        field_size = 0
        number_of_fields = 0
        for field in self._fields:
            number_of_fields += 1
            field_length = await field.content_length()
            if field_length is None:
                return None
            field_size += field_length
        return ((6 + len(self.boundary)) * (number_of_fields + 1)) + field_size

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        boundary_bytes = self.boundary.encode()
        for field in self._fields:
            yield b"--%b\r\n%b" % (boundary_bytes, field.render_headers())
            async for chunk in (await field.data_chunks()):
                yield chunk
            yield b"\r\n"
        yield b"--%b--\r\n" % boundary_bytes

    @property
    def content_type(self) -> str:
        return f"multipart/form-data; boundary={self.boundary}"

    @property
    def boundary(self) -> str:
        if self._boundary is None:
            self._boundary = binascii.hexlify(os.urandom(16)).decode()
        return self._boundary
