import ssl
import trio
import hip
import json
from hip._backends import get_backend
from hip._async.transaction import HTTP11Transaction


async def main():

    # Construct the Request manually (will be handled by Session)
    async def data():
        yield b"Hello!"

    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/anything")
    req = hip.Request(
        "POST",
        url,
        headers={
            "host": "httpbin.org",
            "accept": "*/*",
            "user-agent": "python-hip/0",
            "expect": "100-continue",
            "content-length": "6",
        },
    )
    req.target = "/anything"
    data_iter = data()
    scheme, host, port = req.url.origin

    # Load the Backend, create a Socket, then hand socket to HTTP/1.1 Transaction
    # (will be handled by Connection/Transaction Manager)
    backend = get_backend(is_async=True)
    socket = await backend.connect(host, port, connect_timeout=10.0)
    if scheme == "https":
        socket = await socket.start_tls(
            server_hostname=host, ssl_context=ssl.create_default_context()
        )

    trans = HTTP11Transaction(socket)

    # With the Transaction send the Request and stream Response data
    # (will be handled by Session)
    resp = await trans.send_request(request=req, request_data=data_iter)
    print("response=", resp)
    print("request=", req)
    print("headers=", resp.headers)
    print("history=", resp.history)

    resp_json = await resp.json()
    print("json=", json.dumps(resp_json, sort_keys=True, indent=2))


trio.run(main)
