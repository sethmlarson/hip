import typing
from .models import (
    JSON,
    JSONType,
    RequestData,
    URLEncodedForm,
    AuthType,
    DataType,
    Bytes,
    NoData,
)
from .models import Response
from .transaction import HTTP11Transaction
from hip._backends import get_backend
from hip.models import (
    Request,
    ParamsType,
    HeadersType,
    TimeoutType,
    ProxiesType,
    RetriesType,
    RedirectsType,
    TLSVersion,
    CACertsType,
    PinnedCertsType,
    CookiesType,
    URLType,
)


class Session:
    """
    The central instance that manages HTTP life-cycles and interfaces
    with the background connection pools.
    Adding all of the shortened 'per-method' functions to the
    Session can be done later once the entire interface is complete.
    Until that time they are basically just dead-weight for testing
    and updating.
    """

    def __init__(
        self,
        *,
        headers: typing.Optional[HeadersType] = None,
        auth: typing.Optional[AuthType] = None,
        retries: typing.Optional[RetriesType] = None,
        redirects: typing.Optional[RedirectsType] = None,
        timeout: typing.Optional[TimeoutType] = None,
        proxies: typing.Optional[ProxiesType] = None,
        trust_env: bool = True,
        ca_certs: typing.Optional[CACertsType] = None,
        pinned_certs: typing.Optional[PinnedCertsType] = None,
        tls_min_version: typing.Optional[TLSVersion] = TLSVersion.TLSv1_2,
        tls_max_version: typing.Optional[TLSVersion] = TLSVersion.MAXIMUM_SUPPORTED,
        http_versions: typing.Optional[typing.Sequence[str]] = None,
    ):
        self.headers = headers
        self.auth = auth
        self.retries = retries
        self.redirects = redirects
        self.timeout = timeout
        self.proxies = proxies
        self.trust_env = trust_env

        self.ca_certs = ca_certs
        self.pinned_certs = pinned_certs
        self.tls_min_version = tls_min_version
        self.tls_max_version = tls_max_version
        self.http_versions = http_versions

    async def request(
        self,
        # Request Headers
        method: str,
        url: URLType,
        headers: typing.Optional[HeadersType] = None,
        auth: typing.Optional[AuthType] = None,
        cookies: typing.Optional[CookiesType] = None,
        params: typing.Optional[ParamsType] = None,
        # Request Body
        data: typing.Optional[DataType] = None,
        json: typing.Optional[JSONType] = None,
        # Request Lifecycle
        retries: typing.Optional[RetriesType] = None,
        redirects: typing.Optional[typing.Union[int, bool]] = None,
        # Transaction
        timeout: typing.Optional[TimeoutType] = None,
        proxies: typing.Optional[ProxiesType] = None,
        http_versions: typing.Optional[
            typing.Sequence[str]
        ] = None,  # For now we only support HTTP/1.1.
    ) -> Response:
        """Sends a request."""
        request = self.prepare_request(
            method=method,
            url=url,
            headers=headers,
            auth=auth,
            cookies=cookies,
            params=params,
        )
        request_data = self.prepare_data(data=data, json=json)

        # Set the framing headers
        content_length = await request_data.content_length()
        if content_length is None:
            request.headers.setdefault("transfer-encoding", "chunked")
        else:
            request.headers.setdefault("content-length", str(content_length))

        content_type = request_data.content_type
        if content_type is not None:
            request.headers.setdefault("content-type", content_type)

        request.headers.setdefault("host", request.url.host)
        request.headers.setdefault("accept", "*/*")
        request.headers.setdefault("user-agent", "python-hip/0")

        backend = get_backend(True)
        scheme, host, port = request.url.origin
        socket = await backend.connect(host, port, connect_timeout=10.0)
        if scheme == "https":
            import ssl

            socket = await socket.start_tls(
                server_hostname=host, ssl_context=ssl.create_default_context()
            )

        transaction = HTTP11Transaction(socket)
        resp = await transaction.send_request(
            request, (await request_data.data_chunks())
        )
        return resp

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
        """
        request = Request(method=method, url=url, headers=headers)
        if auth:
            request = auth(request)

        return request

    def prepare_data(self, data: DataType = None, json: JSONType = None) -> RequestData:
        """Changes the 'data' and 'json' parameters into a 'RequestData'
        object that handles the many different data types that we support.
        """
        if data is not None and json is not None:
            raise ValueError("!")

        if json is not None:
            return JSON(json)
        elif data is None:
            return NoData()
        elif isinstance(data, (dict, list)):
            return URLEncodedForm(data)
        elif isinstance(data, bytes):
            return Bytes(data)
        elif isinstance(data, str):
            return Bytes(data.encode("utf-8"))
        # TODO: File-like objects
