import typing
import http.cookiejar
import http.cookies
from .models import Request, Response


http.cookies.Morsel()

CookiesType = typing.Union[
    typing.Mapping[str, str], http.cookiejar.CookieJar, "Cookies"
]


class _Urllib2Request:
    """Wraps a 'hip.Request' so that it looks like a 'urllib2.Request'

    A note from the Python docs on which methods we need to support:

    > The request object (usually a urllib.request.Request instance) must support
    > the methods get_full_url(), get_host(), get_type(), unverifiable(), has_header(),
    > get_header(), header_items(), add_unredirected_header() and origin_req_host
    > attribute as documented by urllib.request.
    """

    def __init__(self, request: Request):
        self._request = request
        self._new_headers: typing.Dict[str, str] = {}

    def get_host(self) -> str:
        return self._request.url.host

    def get_full_url(self) -> str:
        return str(self._request.url)

    @property
    def origin_req_host(self) -> str:
        return self.get_host()

    @property
    def unverifiable(self) -> bool:
        return True

    def has_header(self, name: str) -> bool:
        return name in self._request.headers or name in self._new_headers

    def get_header(
        self, name: str, default: typing.Optional[str] = None
    ) -> typing.Optional[str]:
        return self._request.headers.get(
            name, default=self._new_headers.get(name, default=default)
        )

    def add_unredirected_header(self, name: str, value: str) -> None:
        self._new_headers[name] = value

    def get_new_headers(self) -> typing.Dict[str, str]:
        return self._new_headers


class _Urllib2Response:
    """Wraps a 'hip.Response' so it looks like an 'http.HTTPMessage'"""

    def __init__(self, response: Response):
        self._response = response

    def info(self):
        return self._response.headers


class Cookies:
    """A wrapper around an http.cookiejar.CookieJar()"""

    def __init__(self, jar: typing.Optional[CookiesType] = None):
        if jar is None:
            jar = http.cookiejar.CookieJar()
        elif isinstance(jar, Cookies):
            jar = jar.jar
        self.jar = jar

    def set(
        self,
        name: str,
        value: str,
        domain: typing.Optional[str] = None,
        path: typing.Optional[str] = None,
    ) -> None:
        ...

    def get(
        self,
        name: str,
        default: typing.Optional[str],
        domain: typing.Optional[str] = None,
        path: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        ...

    def keys(self) -> typing.Iterator[str]:
        return iter(self.jar.keys())

    def values(self) -> typing.Iterator[str]:
        return iter(self.jar.values())

    def items(self) -> typing.Iterator[typing.Tuple[str, str]]:
        return iter(self.jar.items())
