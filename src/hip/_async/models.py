import os
import binascii
import typing
import json
from ..models import HeadersType, Request
from ..utils import INT_TO_URLENC


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

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        """Factory object for creating an iterable over the wrapped object.
        If the internal data is not rewindable and this function is called
        then a 'hip.UnrewindableBodyError' is raised.
        """
        raise NotImplementedError()

    @property
    def content_type(self) -> str:
        raise NotImplementedError()


class JSON(RequestData):
    def __init__(self, json, json_dumps=json.dumps):
        self._json = json
        self._json_dumps = json_dumps
        self._data: typing.Optional[bytes] = None

    async def content_length(self) -> typing.Optional[int]:
        return len(self._encode_json())

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        yield self._encode_json()

    @property
    def content_type(self) -> str:
        return "application/json"

    def _encode_json(self) -> bytes:
        if self._data is None:
            self._data = self._json_dumps(self._json)
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

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        yield self._encode_form()

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
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[HeadersType] = None,
    ):
        self.name = name
        self.data = data
        self.filename = filename
        self.headers = headers
        self._content_type = content_type

    def render_headers(self) -> bytes:
        ...

    async def content_length(self) -> int:
        ...

    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        ...

    @property
    def content_type(self) -> str:
        return self._content_type or "application/octet-stream"


class MultipartForm(RequestData):
    """Implements multipart/form-data as a RequestData object"""

    def __init__(self, form):
        self._form = form
        self._boundary: typing.Optional[str] = None

    def add_field(
        self,
        name: str,
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
        return 6 + len(self.boundary)

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
            self._boundary = binascii.hexlify(os.urandom(16))
        return self._boundary

    def _iter_fields(self) -> typing.Iterable[MultipartFormField]:
        ...
