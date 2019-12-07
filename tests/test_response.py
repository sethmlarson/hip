import pytest
import hip


@pytest.mark.parametrize("raw", [(), (b"",)])
@pytest.mark.parametrize(
    "headers", [{"content-length": "0"}, {"transfer-encoding": "chunked"}]
)
def test_empty_response(raw, headers):
    resp = hip.s.Response(
        status_code=200, headers=headers, http_version="HTTP/1.1", raw_data=iter(raw),
    )

    assert resp.data() == b""
    assert resp.text() == ""
    assert resp.encoding == "ascii"


@pytest.mark.parametrize("charset", ["ascii", "utf-8", "UTF-8", '"utf-8"', '"UTF-8"'])
def test_response_content_type_charset(charset):
    resp = hip.s.Response(
        status_code=200,
        headers={"content-type": f"text/plain; charset={charset}"},
        http_version="HTTP/1.1",
        raw_data=iter(()),
    )

    assert resp.data() == b""
    assert resp.text() == ""
    assert resp.encoding == "ascii" if charset == "ascii" else "utf-8"
