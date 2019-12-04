import typing
from .sessions import Session
from .models import AuthType, JSONType, DataType
from hip.models import (
    AsyncResponse as Response,
    ParamsType,
    HeadersType,
    TimeoutType,
    ProxiesType,
    RetriesType,
    RedirectsType,
    CookiesType,
)


async def request(
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
    redirects: typing.Optional[RedirectsType] = None,
    # Transaction
    timeout: typing.Optional[TimeoutType] = None,
    proxies: typing.Optional[ProxiesType] = None,
    http_versions: typing.Optional[typing.Sequence[str]] = None,
) -> Response:
    return await Session().request(method, url)
