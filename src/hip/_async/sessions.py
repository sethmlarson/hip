import typing


# TODO: Replace all of these with their real types.
HeadersType = typing.Any
Request = typing.Any
AsyncRequestData = typing.Any
Cookies = typing.Any
AsyncResponse = typing.Any
ProxiesType = typing.Any
TimeoutType = typing.Any
RetriesType = typing.Any

AuthType = typing.Union[
    typing.Tuple[typing.Union[str, bytes], typing.Union[str, bytes]],
    typing.Callable[[Request], Request],
    # unasync needs to change typing.Awaitable[X] -> X
    typing.Callable[[Request], typing.Awaitable[Request]],
]
ParamsType = typing.Union[
    typing.Sequence[typing.Union[typing.Tuple[str], typing.Tuple[str, str]]],
    typing.Mapping[str, typing.Optional[str]],
]
CookiesType = typing.Union[
    typing.Mapping[str, str], Cookies,
]
DataType = typing.Union[
    typing.Union[str, bytes],
    typing.BinaryIO,
    typing.TextIO,
    typing.Iterable[typing.Union[str, bytes]],
    # This needs to get unasync-ed into 'typing.Iterable[typing.Union[str, bytes]]'
    typing.AsyncIterable[typing.Union[str, bytes]],
    # This needs to get unasync-ed into 'SyncRequestData'
    AsyncRequestData,
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


class Session:
    """
    The central instance that manages HTTP life-cycles and interfaces
    with the background connection pools.

    Adding all of the shortened 'per-method' functions to the
    Session can be done later once the entire interface is complete.
    Until that time they are basically just dead-weight for testing
    and updating.
    """

    def __init__(self, trust_env: bool = True):
        self.trust_env = trust_env

    async def request(
        self,
        # Request Headers
        method: str,
        url: str,
        headers: typing.Optional[HeadersType] = None,
        auth: typing.Optional[AuthType] = None,
        cookies: typing.Optional[CookiesType] = None,
        params: typing.Optional[ParamsType] = None,
        # Request Body
        data: typing.Optional[DataType] = None,
        json: typing.Optional[JSONType] = None,
        # Connection
        timeout: typing.Optional[TimeoutType] = None,
        proxies: typing.Optional[ProxiesType] = None,
        http_versions: typing.Optional[typing.Sequence[str]] = None,
        # Lifecycle
        retries: typing.Optional[RetriesType] = None,
        redirects: typing.Optional[typing.Union[int, bool]] = None,
    ) -> AsyncResponse:
        """Sends a request."""
        ...

    def prepare_request(
        self,
        method: str,
        url: str,
        headers: typing.Optional[HeadersType] = None,
        auth: typing.Optional[AuthType] = None,
        cookies: typing.Optional[CookiesType] = None,
        params: typing.Optional[ParamsType] = None,
    ) -> Request:
        """Given all components that contribute to a request sans-body
        create a Request instance. This method takes all the information from
        the 'Session' and merges it with info from the .request() call.

        The merging that Requests does is essentially: request() overwrites Session
        level, for 'headers', 'cookies', and 'params' merge the dictionaries and if you
        receive a value of 'None' for a key at the request() level then you
        pop that key out of the mapping.

        People seem to understand this merging strategy.

        One edge-case that has been brought up is how to set an 'empty' value
        versus a 'key without a value' in query string.
        See this long issue: https://github.com/psf/requests/issues/2651

        - Requests 2 has: {'k': ''} -> '?k=', {'k': None} -> None so there's no way to create '?k'
        - "Requests 3" has "accepted" this solution: {'k': ''} -> '?k' but then there's suddenly no
          way to create '?k=' so... doesn't seem like a solution.
        - I'm proposing we allow [('k',)] -> '?k'?

        aiohttp also allows passing a raw string that isn't encoded at all.
        I'm guessing if we did this we wouldn't do any merging, would just replace?
        """
        ...

    def prepare_data(
        self, data: DataType = None, json: JSONType = None
    ) -> AsyncRequestData:
        """Changes the 'data' and 'json' parameters into a 'RequestData'
        object that handles the many different data types that we support.
        """
        ...
