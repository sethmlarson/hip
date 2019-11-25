import typing

HeadersType = typing.Union[
    typing.Mapping[str, str],
    typing.Mapping[bytes, bytes],
    typing.Iterable[typing.Tuple[str, str]],
    typing.Iterable[typing.Tuple[bytes, bytes]],
]

class SyncRequestData:
    """Represents a synchronous request data object. Basically a wrapper around whatever
    a user passes in via 'data', 'files', 'json', etc parameters. We can take bytes /
    strings, iterators of bytes or strings, and files. We can also sub-class / implement
    a file-like interface for things like multipart-formdata so it's possible to
    rewind (unlike the current urllib3 interface).

    Maybe in the future we can expose details about when an object can be sent via
    'socket.sendfile()', etc. This would have to be communicated somehow to the
    low-level backend streams.

    When we're handed a file-like object we should take down the starting point
    in the file via .tell() so we can rewind and put the pointer back after
    the seek() call in '.content_length'

    Ref: https://github.com/python-trio/urllib3/issues/135
    """

    def read(self, nbytes: int) -> bytes:
        """Don't know what to call this? Grab some data from the pool of data
        to be sent across the wire.
        """
    @property
    def content_length(self) -> typing.Optional[int]:
        """We can get a proper content-length for bytes, strings, file-like objects
        that are opened in binary mode (is that detectable somehow?). If we hand
        back 'None' from this property it means that the request should use
        'Transfer-Encoding: chunked'
        """
    def rewind(self) -> None:
        """This function rewinds the request data so that it can be retransmitted
        in the case of a timeout/socket error on an idempotent request, a redirect,
        etc so that the new request can be sent. This works for file-like objects
        and bytes / strings (where it's a no-op).
        """
    @property
    def is_rewindable(self) -> bool:
        """We should return a bool whether .rewind() will explode or not."""

class AsyncRequestData(SyncRequestData):
    """The same as above except also accepts async files (we'll have to
    handle all the possible APIs here?) and async iterators.
    """

    async def read(self, nbytes: int) -> bytes: ...
    async def rewind(self) -> None: ...

class Request:
    """Requests aren't painted async or sync, only their data is.
    By the time the request has been sent on the network and we'll
    get a response back the request will be attached to the response
    via 'SyncResponse.request'. At that point we can remove the 'data'
    parameter from the Request and only have the metadata left so
    users can't muck around with a spent Request body.

    The 'url' type now is just a string but will be a full-featured
    type in the future. Requests has 'Request.url' as a string but
    we'll want to expose the whole URL object to do things like
    'request.url.origin' downstream.

    Also no reason to store HTTP version here as the final version
    of the request will be determined after the connection has
    been established.
    """

    def __init__(
        self,
        method: str,
        url: str,
        headers: HeadersType,
        data: typing.Union[SyncRequestData, AsyncRequestData]=None,
    ): ...
