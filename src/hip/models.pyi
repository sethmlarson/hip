import typing

URL = typing.Any
Headers = typing.Any

URLType = typing.Union[str, URL]
HeadersType = typing.Union[
    typing.Mapping[str, str],
    typing.Mapping[bytes, bytes],
    typing.Iterable[typing.Tuple[str, str]],
    typing.Iterable[typing.Tuple[bytes, bytes]],
    Headers,
]

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

    We allow setting Request.target = '*' for both OPTIONS requests
    and for HTTP proxies providing the target in absolute form.
    If unset Request.target defaults to Request.url.path + ('?' + Request.url.params)?
    """

    def __init__(self, method: str, url: URLType, *, headers: HeadersType = None,): ...
    @property
    def url(self) -> URL: ...
    @url.setter
    def url(self, value: URLType) -> None: ...
    @property
    def headers(self) -> Headers: ...
    @headers.setter
    def headers(self, value: HeadersType) -> Headers: ...
    @property
    def target(self) -> str: ...
    @target.setter
    def target(self, value: str) -> None: ...
