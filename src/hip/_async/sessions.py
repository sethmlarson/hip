import typing


HeadersType = typing.Any  # TODO: Replace with the real HeadersType from 'models'
Request = typing.Any  # TODO: Replace with the real Request type
AsyncRequestData = typing.Any  # TODO: Replace with the AsyncRequestData type
Cookies = typing.Any  # TODO: Replace with real Cookies type

QueryType = typing.Union[
    typing.Sequence[typing.Tuple[str], typing.Tuple[str, str]],
    typing.Mapping[str, typing.Optional[str]],
]
CookiesType = typing.Union[
    typing.Mapping[str, str], Cookies,
]
DataType = typing.Union[
    typing.AnyStr,
    typing.BinaryIO,
    typing.TextIO,
    typing.Iterable[typing.AnyStr],
    # This needs to get unasync-ed into 'typing.Iterable[typing.AnyStr]'
    typing.AsyncIterable[typing.AnyStr],
    # This needs to get unasync-ed into 'SyncRequestData'
    AsyncRequestData,
]
JSONType = typing.Union[
    typing.Mapping["JSONType", "JSONType"],
    typing.Sequence["JSONType"],
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
        headers: HeadersType = None,
        auth=None,
        cookies: CookiesType = None,
        query: QueryType = None,
        # Request Body
        data: DataType = None,
        json: JSONType = None,
        # Connection
        timeout=None,
        proxies=None,
        http_versions: typing.Sequence[str] = None,
        # Lifecycle
        retries=None,
        redirects: typing.Union[int, bool] = None,
    ):
        """Sends a request."""
        ...

    def prepare_request(
        self, method: str, url: str, headers=None, auth=None, cookies=None, query=None
    ) -> Request:
        """Given all components that contribute to a request sans-body
        create a Request instance. This method takes all the information from
        the 'Session' and merges it with info from the .request() call.

        I've renamed 'params' to 'query' because I never understood the name 'params'.
        Maybe that's just me and we should keep it params?

        The merging that Requests does is essentially: request() overwrites Session
        level, for 'headers', 'cookies', and 'query' merge the dictionaries and if you
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
