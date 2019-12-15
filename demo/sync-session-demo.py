import hip
import time


def main():
    t = time.time()
    http = hip.s.Session()
    for _ in range(100):
        resp = http.request("HEAD", "https://httpbin.org/anything")
        resp.close()

    print(time.time() - t)


main()
