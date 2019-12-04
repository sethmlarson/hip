import hip
import trio


http = hip.a.Session()


async def main():
    await top_level_request()
    await stream_bytes()
    await stream_text()
    await json()
    await expect_100_continue()


async def top_level_request():
    resp = await hip.a.request("GET", "https://www.example.com")
    print(resp.status_code, resp.headers, (await resp.text()))


async def stream_bytes():
    resp = await http.request("GET", "https://www.example.com")
    print(resp.status_code, resp.headers)
    async for chunk in resp.stream():
        print(chunk)


async def stream_text():
    resp = await http.request()


trio.run(main)
