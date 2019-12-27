import typing
from .sessions import Session
from .models import AuthType, JSONType, DataType, Response
from hip.models import (
    ParamsType,
    HeadersType,
    TimeoutType,
    ProxiesType,
    RetriesType,
    RedirectsType,
)
from hip.cookies import CookiesType


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
    server_hostname: typing.Optional[str] = None,
    timeout: typing.Optional[TimeoutType] = None,
    proxies: typing.Optional[ProxiesType] = None,
    http_versions: typing.Optional[typing.Sequence[str]] = None,
) -> Response:
    return await Session().request(
        method,
        url,
        headers=headers,
        auth=auth,
        cookies=cookies,
        params=params,
        data=data,
        json=json,
        retries=retries,
        redirects=redirects,
        server_hostname=server_hostname,
        timeout=timeout,
        proxies=proxies,
        http_versions=http_versions,
    )
