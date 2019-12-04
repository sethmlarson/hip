import typing
from .models import JSON, JSONType, RequestData, URLEncodedForm, AuthType, DataType
from hip.models import (
    Request,
    AsyncResponse as Response,
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
        url: str,
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

        # TODO: Create an HTTPTransaction
        while True:
            transaction = transaction_manager.start_http_transaction(request)

            async def sending():
                nonlocal request_data
                async for chunk in (await request_data.data_chunks()):
                    await transaction.send_request_data(chunk)
                await transaction.send_eof()

            async def receiving():
                yield await transaction.receive_response_headers()
                chunk = await transaction.receive_response_data()
                while chunk:
                    yield chunk
                    chunk = await transaction.receive_response_data()

            # Send and Receive here

            await transaction.close()

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
        elif isinstance(data, (dict, list)):
            return URLEncodedForm(data)
