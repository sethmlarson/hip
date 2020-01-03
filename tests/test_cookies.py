import pytest
import hip


@pytest.mark.parametrize(
    ["set_cookie", "expected"],
    [
        ({"set-cookie": "k=v"}, [("k", "v")]),
        # Multiple 'Set-Cookie' headers
        ([("set-cookie", "k=v"), ("set-cookie", "k2=v2")], [("k", "v"), ("k2", "v2")]),
        # Directives don't interfere
        ({"set-cookie": "key=val; HttpOnly"}, [("key", "val")]),
        # Cookie is marked 'Secure' over 'http://...'
        ({"set-cookie": "key=val; Secure;"}, []),
        ({"set-cookie": "key=val; HttpOnly; Secure"}, []),
        # Cookie is already expired
        ({"set-cookie": "key=val; Expires=Wed, 21 Oct 2015 07:28:00 GMT"}, []),
    ],
)
def test_extract_cookies(set_cookie, expected):
    cookies = hip.Cookies()
    req = hip.Request("GET", "http://example.com")
    resp = hip.Response(200, "HTTP/1.1", set_cookie, request=req)
    cookies.extract_cookies_to_jar(resp)

    assert list(cookies.items()) == expected


def test_set_cookie_domain_public_domain():
    cookies = hip.Cookies()
    req = hip.Request("GET", "https://cloudfunctions.net")
    resp = hip.Response(
        200, "HTTP/1.1", {"set-cookie": "k=v; Domain=cloudfunctions.net"}, request=req
    )
    cookies.extract_cookies_to_jar(resp)

    assert list(cookies.items()) == []


def test_set_cookie_domain_private_domain():
    cookies = hip.Cookies()
    req = hip.Request("GET", "https://abc.cloudfunctions.net")
    resp = hip.Response(
        200,
        "HTTP/1.1",
        {"set-cookie": "k=v; Domain=abc.cloudfunctions.net"},
        request=req,
    )
    cookies.extract_cookies_to_jar(resp)

    assert list(cookies.items()) == [("k", "v")]


@pytest.mark.parametrize(
    ["scheme", "secure", "expected"],
    [
        ("https", True, True),
        ("http", True, False),
        ("https", False, False),
        ("http", False, False),
    ],
)
def test_set_cookie__secure_prefix(scheme, secure, expected):
    cookies = hip.Cookies()
    req = hip.Request("GET", f"{scheme}://example.com")
    resp = hip.Response(
        200,
        "HTTP/1.1",
        {"set-cookie": f"__Secure-k=v{'; Secure' if secure else ''}"},
        request=req,
    )
    cookies.extract_cookies_to_jar(resp)

    assert list(cookies.items()) == ([("__Secure-k", "v")] if expected else [])


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("secure", [True, False])
@pytest.mark.parametrize("domain", [True, False])
@pytest.mark.parametrize("path", [False, "/path", "/"])
def test_set_cookie__host_prefix(scheme, secure, domain, path):
    cookies = hip.Cookies()
    req = hip.Request("GET", f"{scheme}://example.com")

    cookie_parts = ["__Host-k=v"]
    if secure:
        cookie_parts.append("Secure")
    if domain:
        cookie_parts.append("Domain=example.com")
    if path:
        cookie_parts.append(f"Path={path}")

    resp = hip.Response(
        200, "HTTP/1.1", {"set-cookie": "; ".join(cookie_parts)}, request=req,
    )
    cookies.extract_cookies_to_jar(resp)

    assert list(cookies.items()) == (
        [("__Host-k", "v")]
        if (scheme, secure, domain, path) == ("https", True, False, "/")
        else []
    )
