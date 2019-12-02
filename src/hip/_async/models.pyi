import typing

class RequestData:
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
    the seek() call in '.content_length()'

    Ref: https://github.com/python-trio/urllib3/issues/135
    """

    async def content_length(self) -> typing.Optional[int]:
        """We can get a proper content-length for bytes, strings, file-like objects
        that are opened in binary mode (is that detectable somehow?). If we hand
        back 'None' from this property it means that the request should use
        'Transfer-Encoding: chunked'
        """
    async def data_chunks(self) -> typing.AsyncIterable[bytes]:
        """Factory object for creating an iterable over the wrapped object.
        If the internal data is not rewindable and this function is called
        then a 'hip.UnrewindableBodyError' is raised.
        """
