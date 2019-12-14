import json
import hip
import time


def main():
    t = time.time()
    http = hip.s.Session()
    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/absolute-redirect/10")
    resp = http.request("GET", url, redirects=10)

    print(time.time() - t)
    print(resp.status_code)
    print(resp.headers)
    print(resp.history)
    print(resp.request)
    resp_json = resp.json()
    print(json.dumps(resp_json, sort_keys=True, indent=2))


main()
