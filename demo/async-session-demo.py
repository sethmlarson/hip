import json
import hip
import trio


async def main():
    import time
    t = time.time()
    http = hip.a.Session()
    for _ in range(50):
        url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/bytes/10000")
        resp = await http.request("GET", url)
        await resp.close()

        #print(resp.status_code)
        #print(resp.headers)
        #print(resp.history)
        #print(resp.request)
        #async for chunk in resp.stream():
        #    print(len(chunk))
        #resp_json = await resp.json()
        #print(json.dumps(resp_json, sort_keys=True, indent=2))

    print(time.time() - t)


trio.run(main)
