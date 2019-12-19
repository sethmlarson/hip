import hip
import trio
import time


async def task(http):
    resp = await http.request("GET", "https://www.google.com")
    await resp.close()


async def main():
    t = time.time()
    http = hip.a.Session()
    async with trio.open_nursery() as nursery:
        for _ in range(100):
            nursery.start_soon(task, http)
    print(time.time() - t)


trio.run(main)
