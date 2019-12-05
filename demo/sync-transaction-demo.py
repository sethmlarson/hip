import ssl
import hip
import json
from hip._backends import get_backend
from hip._sync.transaction import HTTP11Transaction


def main():

    # Construct the Request manually (will be handled by Session)
    def data():
        yield b"Hello!"

    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/anything")
    req = hip.Request(
        "POST",
        url,
        headers={
            "host": "httpbin.org",
            "accept": "*/*",
            "user-agent": "python-hip/0",
            "content-length": "6",
        },
    )
    req.target = "/anything"
    data_iter = data()
    scheme, host, port = req.url.origin

    # Load the Backend, create a Socket, then hand socket to HTTP/1.1 Transaction
    # (will be handled by Connection/Transaction Manager)
    backend = get_backend(is_async=False)
    socket = backend.connect(host, port, connect_timeout=10.0)
    if scheme == "https":
        socket = socket.start_tls(
            server_hostname=host, ssl_context=ssl.create_default_context()
        )

    trans = HTTP11Transaction(socket)

    # With the Transaction send the Request and stream Response data
    # (will be handled by Session)
    resp = trans.send_request(request=req, request_data=data_iter)
    resp.encoding = "utf-8"  # Have to set this manually as encoding isn't determined automatically yet.
    print("response=", resp)
    print("request=", req)
    print("headers=", resp.headers)
    print("history=", resp.history)

    resp_json = resp.json()
    print("json=", json.dumps(resp_json, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
