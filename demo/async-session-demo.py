import hip
import trio
import time


async def main():
    t = time.time()
    http = hip.a.Session()
    for _ in range(100):
        resp = await http.request("HEAD", "https://httpbin.org/anything")
        await resp.close()

    print(time.time() - t)


trio.run(main)
