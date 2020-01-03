import typing
import http.cookiejar
import http.cookies
import psl
from .models import Request, Response, Headers

CookiesType = typing.Union[
    typing.Mapping[str, str], http.cookiejar.CookieJar, "Cookies"
]


class HipCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    def set_ok(
        self, cookie: http.cookiejar.Cookie, request: "_CookiejarCompatibleRequest"
    ) -> bool:
        if not super().set_ok(cookie, request):
            return False

        # If we receive a cookie with 'Secure' from a non-secure context
        # we shouldn't add it to the cookie jar. Wait until a request is
        # made in a secure context.
        cookie_secure = getattr(cookie, "secure", False)
        if cookie_secure and not request.get_full_url().startswith("https://"):
            return False

        # If a cookie is prefixed with '__Host-' and doesn't have
        # a 'Secure' directive, defines a 'Domain' directive or
        # has no 'Path' directive or one not equal to '/' then don't accept it.
        if cookie.name.startswith("__Host-") and (
            not cookie_secure
            or cookie.domain_specified
            or not cookie.path_specified
            or cookie.path != "/"
        ):
            return False

        # If a cookie is prefixed with '__Secure-' and isn't received
        # with a 'Secure' context then don't accept it.
        if cookie.name.startswith("__Secure-") and not cookie_secure:
            return False

        # Check to see if the domain can be set to a given 'Domain' value
        # on the cookie. This disables super-cookies that propagate over
        # multiple distinct services. (eg *.cloudfunctions.net)
        return psl.domain_can_set_cookie(cookie.domain)


class _CookiejarCompatibleRequest:
    """Wraps a 'hip.Request' so that it looks like a 'urllib.request.Request'

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
        return name in self._request.headers or name.lower() in self._new_headers

    def get_header(
        self, name: str, default: typing.Optional[str] = None
    ) -> typing.Optional[str]:
        return self._request.headers.get(
            name, default=self._new_headers.get(name.lower(), default=default)
        )

    def add_unredirected_header(self, name: str, value: str) -> None:
        self._new_headers[name.lower()] = value

    def get_cookie_header(self) -> typing.Optional[str]:
        return self._new_headers.get("cookie", None)


class _CookiejarCompatibleResponse:
    """Wraps a 'hip.Response' so it looks like an 'http.HTTPMessage'"""

    def __init__(self, response: Response):
        self._response = response

    def info(self) -> Headers:
        return self._response.headers


class Cookies:
    """A wrapper around an http.cookiejar.CookieJar()"""

    def __init__(self, jar: typing.Optional[CookiesType] = None):
        if jar is None:
            jar = http.cookiejar.CookieJar(policy=HipCookiePolicy())
        elif isinstance(jar, dict):
            jar = http.cookiejar.CookieJar(policy=HipCookiePolicy())
        elif isinstance(jar, Cookies):
            jar = jar.jar

        self.jar: http.cookiejar.CookieJar = jar

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
        default: typing.Optional[str] = None,
        domain: typing.Optional[str] = None,
        path: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        ...

    def extract_cookies_to_jar(self, response: Response) -> None:
        compat_req = _CookiejarCompatibleRequest(response.request)
        compat_res = _CookiejarCompatibleResponse(response)
        self.jar.extract_cookies(request=compat_req, response=compat_res)

    def get_cookie_header(self, request: Request) -> typing.Optional[str]:
        compat_req = _CookiejarCompatibleRequest(request)
        self.jar.add_cookie_header(compat_req)
        return compat_req.get_cookie_header()

    def keys(self) -> typing.Iterator[str]:
        return iter(k for k, _ in self.items())

    def values(self) -> typing.Iterator[str]:
        return iter((v for _, v in self.items()))

    def items(self) -> typing.Iterator[typing.Tuple[str, str]]:
        for cookie in self.cookies():
            yield cookie.name, cookie.value

    def cookies(self) -> typing.Iterator[http.cookiejar.Cookie]:
        return iter(self.jar)

    def __repr__(self) -> str:
        return f"<Cookies {list(self.cookies())}>"

    __str__ = __repr__
