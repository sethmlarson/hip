"""Module that exists solely because the sync interface
for response is slightly different than the async.
"""

import typing

try:
    from ._sync import Response as _Response
    from ._sync import (
        RequestData,
        URLEncodedForm,
        MultipartForm,
        JSON,
        Session,
        request,
    )
except ImportError:
    _Response = object

__all__ = [
    "RequestData",
    "URLEncodedForm",
    "MultipartForm",
    "JSON",
    "Session",
    "Response",
    "request",
]


class Response(_Response):
    """Synchronous response has the 'as_file()' interface to easily be passed into
    interfaces that require a file-like input. The file-like object that is
    returned transparently streams from the response and then closes the response
    at the end of the stream while maintaining the file-like object in the 'open'
    state. Many interfaces like csv.DictReader() rely on the file-like object staying open
    after being read unlike the Response interface.
    """

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
