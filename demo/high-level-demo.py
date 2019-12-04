import hip
import trio


http = hip.a.Session()


async def main():
    resp = await http.request("GET", "https://www.example.com")
    print(resp.status_code, resp.headers)
    async for chunk in resp.stream():
        print(chunk)


trio.run(main)
