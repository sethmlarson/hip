import pytest
import hip


@pytest.mark.trio
async def test_single_redirect():
    resp = await hip.a.request(
        "GET", "https://httpbin.org/absolute-redirect/1", redirects=1
    )

    assert resp.status_code == 200
    assert "location" not in resp.headers
    assert resp.request.method == "GET"
    assert resp.request.url == "http://httpbin.org/get"
    assert resp.request.headers["host"] == "httpbin.org"

    assert len(resp.history) == 1
    redirect_resp = resp.history[0]
    assert resp.request.url == redirect_resp.headers["location"]
    assert redirect_resp.status_code == 302
    assert redirect_resp.request.method == "GET"
    assert redirect_resp.request.url == "https://httpbin.org/absolute-redirect/1"
    assert redirect_resp.request.headers["host"] == "httpbin.org"


@pytest.mark.trio
async def test_disable_automatic_redirects():
    resp = await hip.a.request(
        "GET", "https://httpbin.org/absolute-redirect/1", redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://httpbin.org/get"
    assert resp.history == []
    assert resp.request.method == "GET"
    assert resp.request.url == "https://httpbin.org/absolute-redirect/1"
    assert resp.request.headers["host"] == "httpbin.org"


@pytest.mark.trio
async def test_error_on_redirect():
    with pytest.raises(hip.TooManyRedirects) as e:
        await hip.a.request(
            "GET", "https://httpbin.org/absolute-redirect/1", redirects=0
        )

    assert e.value.request.method == "GET"
    assert e.value.request.url == "https://httpbin.org/absolute-redirect/1"

    # The too-many-redirects error should have the redirect response attached
    assert e.value.response.status_code == 302
    assert e.value.response.headers["location"] == "http://httpbin.org/get"
    assert e.value.response.history == []


@pytest.mark.trio
async def test_exact_number_of_redirects():
    resp = await hip.a.request(
        "GET", "https://httpbin.org/absolute-redirect/10", redirects=10
    )

    assert resp.status_code == 200
    assert "location" not in resp.headers
    assert len(resp.history) == 10


@pytest.mark.trio
async def test_n_plus_one_redirects():
    with pytest.raises(hip.TooManyRedirects) as e:
        await hip.a.request(
            "GET", "https://httpbin.org/absolute-redirect/10", redirects=9
        )

    assert e.value.response.status_code == 302
    assert e.value.response.headers["location"] == "http://httpbin.org/get"
    assert len(e.value.response.history) == 9
