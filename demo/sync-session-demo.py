import json
import hip
import trio


def main():
    http = hip.s.Session()
    url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/anything")
    resp = http.request("POST", url, json={"Hello": "world!"})

    print(resp.status_code)
    print(resp.headers)
    resp_json = resp.json()
    print(json.dumps(resp_json, sort_keys=True, indent=2))


main()
