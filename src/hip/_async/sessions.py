import certifi
import io
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
from .models import Response, File
from .manager import ConnectionConfig, BackgroundManager
from .utils import sync_or_async
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
    URL,
    Response as BaseResponse,
)
from hip.decoders import accept_encoding
from hip.exceptions import RedirectLoopDetected, TooManyRedirects, HipError
from hip.utils import user_agent


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
        redirects: typing.Optional[RedirectsType] = True,
        timeout: typing.Optional[TimeoutType] = None,
        proxies: typing.Optional[ProxiesType] = None,
        trust_env: bool = True,
        ca_certs: typing.Optional[CACertsType] = certifi.where(),
        pinned_certs: typing.Optional[PinnedCertsType] = None,
        tls_min_version: TLSVersion = TLSVersion.TLSv1_2,
        tls_max_version: TLSVersion = TLSVersion.MAXIMUM_SUPPORTED,
        http_versions: typing.Sequence[str] = ("HTTP/1.1",),
    ):
        self.headers = headers
        self.auth = auth
        self.retries = retries
        self.redirects = redirects
        self.timeout = timeout
        self.proxies = proxies
        self.trust_env = trust_env

        self.ca_certs = ca_certs
        self.pinned_certs = pinned_certs or {}
        self.tls_min_version = tls_min_version
        self.tls_max_version = tls_max_version
        self.http_versions = http_versions

        self.manager = BackgroundManager()

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
        url = URL.parse(url)
        request = self.prepare_request(
            method=method,
            url=url,
            headers=headers,
            auth=auth,
            cookies=cookies,
            params=params,
        )

        if auth:
            request = await sync_or_async(auth, request)

        request_data = self.prepare_data(data=data, json=json)

        # Set the framing headers if they haven't been set yet.
        if (
            "transfer-encoding" not in request.headers
            and "content-length" not in request.headers
        ):
            content_length = await request_data.content_length()
            if content_length is None:
                request.headers.setdefault("transfer-encoding", "chunked")
            else:
                request.headers.setdefault("content-length", str(content_length))

        if "content-type" not in request.headers:
            request.headers.setdefault("content-type", request_data.content_type)

        host = request.url.host
        pinned_cert = self.pinned_certs.get(host, None)
        if pinned_cert is not None:
            pinned_cert = (host, pinned_cert)

        response_history: typing.List[BaseResponse] = []
        visited_urls = {request.url}
        while True:

            # This section doesn't have a response associated with it
            # so we only add the Request to the potential HipError.
            try:
                conn_config = ConnectionConfig(
                    origin=request.url.origin,
                    http_versions=self.http_versions,
                    ca_certs=self.ca_certs,
                    pinned_cert=pinned_cert,
                    tls_min_version=self.tls_min_version.resolve(),
                    tls_max_version=self.tls_max_version.resolve(),
                )
                transaction = await self.manager.start_http_transaction(conn_config)

                resp = await transaction.send_request(
                    request, (await request_data.data_chunks())
                )
            except HipError as e:
                e.request = request
                raise

            # By this point we've received a response so we
            # add that to any potential exceptions too.
            try:
                # For now we add the individual responses' 1XX
                # history to the global response_history and clear
                # response.history. It'll be added back if this is
                # actually the final response in the life-cycle
                # after checking redirects / retries.
                response_history.extend(resp.history)
                resp.history = []

                if redirects is not False and resp.is_redirect:
                    # This redirect is not the final response
                    # so we add it to the history.
                    response_history.append(
                        BaseResponse(
                            status_code=resp.status_code,
                            http_version=resp.http_version,
                            headers=resp.headers.copy(),
                            request=resp.request,
                        )
                    )
                    if isinstance(redirects, int):
                        if redirects == 0:
                            raise TooManyRedirects("too many redirects")
                        redirects -= 1

                    # Drain the response
                    await resp.close()

                    # Detect when we've already been redirected to a URL before
                    # and if we're redirected again then complain.
                    redirect_request = self.prepare_redirect(request, resp)
                    if redirect_request.url in visited_urls:
                        # Create a list of URLs that we visited to reach this loop
                        # to display to the user.
                        redirected_urls = [
                            str(x.request.url)
                            for x in response_history
                            if x.is_redirect
                        ] + [str(redirect_request.url)]
                        raise RedirectLoopDetected(
                            f"redirect loop detected for {' -> '.join(redirected_urls)}"
                        )
                    visited_urls.add(redirect_request.url)

                    request = redirect_request
                    continue

            except HipError as e:
                if e.request is None:
                    e.request = request
                if e.response is None:
                    e.response = resp
                raise

            # This is actually the response we're returning to the user
            # so add all the responses we've received before this one.
            resp.history = response_history
            return resp

    def prepare_request(
        self,
        method: str,
        url: URL,
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

        if "host" not in request.headers:
            request_host = request.url.host
            request_port = request.url.port
            if (
                request_port is not None
                and request_port
                != request.url.DEFAULT_PORT_BY_SCHEME.get(request.url.scheme, None)
            ):
                request_host += f":{request_port}"
            request.headers.setdefault("host", request_host)

        request.headers.setdefault("accept", "*/*")
        request.headers.setdefault("user-agent", user_agent())
        request.headers.setdefault("accept-encoding", accept_encoding())
        request.headers.setdefault("connection", "keep-alive")

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
        elif isinstance(data, io.BinaryIO) or hasattr(data, "read"):
            return File(data)

    def prepare_redirect(self, request: Request, response: Response) -> Request:
        """Applies the redirect to a request. This includes stripping insecure headers
        if the request is cross-origin and mutating the request method.
        """
        headers = request.headers.copy()
        headers.pop_all("host")  # Remove 'Host' as it may be replaced post-redirect.

        new_request = self.prepare_request(
            method=request.method,
            url=request.url.join(response.headers["location"]),
            headers=headers,
        )

        # Follow what browsers do. 301, 302, and 303 convert POST -> GET
        if 301 <= response.status_code <= 303 and request.method == "POST":
            new_request.method = "GET"

        # Remove 'Authorization' header if origin changes (except for HTTP->HTTPS upgrades)
        if request.url.origin != new_request.url.origin:
            old_scheme, old_host, old_port = request.url.origin
            new_scheme, new_host, new_port = new_request.url.origin
            if not (
                old_scheme == "http"
                and new_scheme == "https"
                and (new_port == old_port or (new_port == 443 and old_port == 80))
            ):
                new_request.headers.pop_all("authorization")

        return new_request
