import trio
import hip
from hip.trio_transaction import HTTP11Transaction


async def main():
    async def data():
        yield b"Hello!"

    trans = HTTP11Transaction()
    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/anything")
    req = hip.Request(
        "GET",
        url,
        headers={
            "host": "httpbin.org",
            "accept": "*/*",
            "user-agent": "python-hip/0",
            "expect": "100-continue",
            "content-length": "6",
        },
    )
    req.target = "/"
    data_iter = data()
    resp = await trans.send_request(request=req, request_data=data_iter)
    print(resp, resp.headers, resp.history)
    async for chunk in trans.receive_response_data(request_data=data_iter):
        print(chunk)


trio.run(main)
