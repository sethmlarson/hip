import io
import hip
import pytest

GIF = b"GIF89a\x01\x00\x01\x00\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"


@pytest.mark.trio
async def test_request_data_file_contents_content_type():
    f = io.BytesIO(GIF)
    resp = await hip.a.request("POST", "https://httpbin.org/anything", data=f)

    assert resp.request.headers["Content-Length"] == "32"
    assert resp.request.headers["Content-Type"] == "image/gif"

    assert resp.status_code == 200
    json = await resp.json()

    assert json["method"] == "POST"
    assert json["headers"]["Content-Length"] == "32"
    assert json["headers"]["Content-Type"] == "image/gif"
    assert (
        json["data"]
        == "data:application/octet-stream;base64,R0lGODlhAQABAAAAACH5BAEAAAAALAAAAAABAAEAAAI="
    )


@pytest.mark.trio
async def test_request_data_file_name_content_type():
    with open(__file__, mode="rb") as f:
        resp = await hip.a.request("POST", "https://httpbin.org/anything", data=f)

    assert int(resp.request.headers["Content-Length"]) > 0
    assert resp.request.headers["Content-Type"] == "text/x-python"

    assert resp.status_code == 200
    json = await resp.json()

    assert json["method"] == "POST"
    assert json["headers"]["Content-Type"] == "text/x-python"
    assert json["headers"]["Content-Length"] == resp.request.headers["Content-Length"]
