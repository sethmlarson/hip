import hip


def main():
    import time
    t = time.time()
    http = hip.s.Session()
    for _ in range(50):
        url = hip.URL(scheme="https", host="httpbin.org", port=443, path="/bytes/10000")
        resp = http.request("GET", url)
        print(resp.status_code, resp.headers)
        resp.close()

        #print(resp.status_code)
        #print(resp.headers)
        #print(resp.history)
        #print(resp.request)
        #async for chunk in resp.stream():
        #    print(len(chunk))
        #resp_json = await resp.json()
        #print(json.dumps(resp_json, sort_keys=True, indent=2))

    print(time.time() - t)


main()
