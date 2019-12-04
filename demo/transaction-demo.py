import trio
import hip
from hip.trio_transaction import HTTP11Transaction


async def main():
    async def data():
        yield b"Hello!"

    trans = HTTP11Transaction()
    url = hip.URL(scheme="http", host="www.example.com", port=80, path="/")
    req = hip.Request(
        "HEAD",
        url,
        headers={
            "host": "www.example.com",
            "accept": "*/*",
            "user-agent": "python-hip/0",
            "expect": "100-continue",
            "content-length": "6",
        },
    )
    req.target = "/"
    resp = await trans.send_request(request=req, request_data=data())
    print(resp, resp.headers, resp.history)


trio.run(main)
