import json
import hip
import trio


async def main():
    http = hip.a.Session()
    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/anything")
    resp = await http.request("GET", url)
    resp.encoding = "utf-8"

    print(resp.status_code)
    print(resp.headers)
    resp_json = await resp.json()
    print(json.dumps(resp_json, sort_keys=True, indent=2))

trio.run(main)
