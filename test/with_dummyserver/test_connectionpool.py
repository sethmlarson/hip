import logging
import socket
import sys
import time
import warnings
import pytest

from .. import TARPIT_HOST, VALID_SOURCE_ADDRESSES, INVALID_SOURCE_ADDRESSES
from ..port_helpers import find_unused_port
from hip import encode_multipart_formdata, HTTPConnectionPool
from hip.exceptions import (
    ConnectTimeoutError,
    EmptyPoolError,
    DecodeError,
    MaxRetryError,
    ReadTimeoutError,
    NewConnectionError,
)
from hip.packages.six import b, u
from hip.packages.six.moves.urllib.parse import urlencode
from hip.util.retry import Retry
from hip.util.timeout import Timeout

from test import SHORT_TIMEOUT, LONG_TIMEOUT
from dummyserver.testcase import HTTPDummyServerTestCase, SocketDummyServerTestCase
from dummyserver.server import NoIPv6Warning, HAS_IPV6_AND_DNS

from threading import Event

pytestmark = pytest.mark.flaky

log = logging.getLogger("hip.connectionpool")
log.setLevel(logging.NOTSET)
log.addHandler(logging.StreamHandler(sys.stdout))


def wait_for_socket(ready_event):
    ready_event.wait()
    ready_event.clear()


class TestConnectionPoolTimeouts(SocketDummyServerTestCase):
    def test_timeout_float(self):
        block_event = Event()
        ready_event = self.start_basic_handler(block_send=block_event, num=2)

        with HTTPConnectionPool(self.host, self.port, retries=False) as pool:
            wait_for_socket(ready_event)
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/", timeout=SHORT_TIMEOUT)
            block_event.set()  # Release block

            # Shouldn't raise this time
            wait_for_socket(ready_event)
            block_event.set()  # Pre-release block
            pool.request("GET", "/", timeout=LONG_TIMEOUT)

    def test_conn_closed(self):
        block_event = Event()
        self.start_basic_handler(block_send=block_event, num=1)

        with HTTPConnectionPool(
            self.host, self.port, timeout=SHORT_TIMEOUT, retries=False
        ) as pool:
            conn = pool._get_conn()
            pool._put_conn(conn)
            try:
                with pytest.raises(ReadTimeoutError):
                    pool.urlopen("GET", "/")
                if conn._sock:
                    with pytest.raises(socket.error):
                        conn.sock.recv(1024)
            finally:
                pool._put_conn(conn)

            block_event.set()

    def test_timeout(self):
        # Requests should time out when expected
        block_event = Event()
        ready_event = self.start_basic_handler(block_send=block_event, num=3)

        # Pool-global timeout
        short_timeout = Timeout(read=SHORT_TIMEOUT)
        with HTTPConnectionPool(
            self.host, self.port, timeout=short_timeout, retries=False
        ) as pool:
            wait_for_socket(ready_event)
            block_event.clear()
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/")
            block_event.set()  # Release request

        # Request-specific timeouts should raise errors
        with HTTPConnectionPool(
            self.host, self.port, timeout=short_timeout, retries=False
        ) as pool:
            wait_for_socket(ready_event)
            now = time.time()
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/", timeout=LONG_TIMEOUT)
            delta = time.time() - now

            message = "timeout was pool-level SHORT_TIMEOUT rather than request-level LONG_TIMEOUT"
            assert delta >= LONG_TIMEOUT, message
            block_event.set()  # Release request

            # Timeout passed directly to request should raise a request timeout
            wait_for_socket(ready_event)
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/", timeout=SHORT_TIMEOUT)
            block_event.set()  # Release request

    def test_connect_timeout(self):
        url = "/"
        host, port = TARPIT_HOST, 80
        timeout = Timeout(connect=SHORT_TIMEOUT)

        # Pool-global timeout
        with HTTPConnectionPool(host, port, timeout=timeout) as pool:
            conn = pool._get_conn()
            with pytest.raises(ConnectTimeoutError):
                pool._make_request(conn, "GET", url)

            # Retries
            retries = Retry(connect=0)
            with pytest.raises(MaxRetryError):
                pool.request("GET", url, retries=retries)

        # Request-specific connection timeouts
        big_timeout = Timeout(read=LONG_TIMEOUT, connect=LONG_TIMEOUT)
        with HTTPConnectionPool(host, port, timeout=big_timeout, retries=False) as pool:
            conn = pool._get_conn()
            with pytest.raises(ConnectTimeoutError):
                pool._make_request(conn, "GET", url, timeout=timeout)

            pool._put_conn(conn)
            with pytest.raises(ConnectTimeoutError):
                pool.request("GET", url, timeout=timeout)

    def test_total_applies_connect(self):
        host, port = TARPIT_HOST, 80

        timeout = Timeout(total=None, connect=SHORT_TIMEOUT)
        with HTTPConnectionPool(host, port, timeout=timeout) as pool:
            conn = pool._get_conn()
        with pytest.raises(ConnectTimeoutError):
            pool._make_request(conn, "GET", "/")

        timeout = Timeout(connect=3, read=5, total=SHORT_TIMEOUT)
        with HTTPConnectionPool(host, port, timeout=timeout) as pool:
            try:
                conn = pool._get_conn()
                with pytest.raises(ConnectTimeoutError):
                    pool._make_request(conn, "GET", "/")
            finally:
                conn.close()

    def test_total_timeout(self):
        block_event = Event()
        ready_event = self.start_basic_handler(block_send=block_event, num=2)

        wait_for_socket(ready_event)
        # This will get the socket to raise an EAGAIN on the read
        timeout = Timeout(connect=3, read=SHORT_TIMEOUT)
        with HTTPConnectionPool(
            self.host, self.port, timeout=timeout, retries=False
        ) as pool:
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/")

            block_event.set()
            wait_for_socket(ready_event)
            block_event.clear()

        # The connect should succeed and this should hit the read timeout
        timeout = Timeout(connect=3, read=5, total=SHORT_TIMEOUT)
        with HTTPConnectionPool(
            self.host, self.port, timeout=timeout, retries=False
        ) as pool:
            with pytest.raises(ReadTimeoutError):
                pool.request("GET", "/")

    def test_create_connection_timeout(self):
        self.start_basic_handler(block_send=Event(), num=0)  # needed for self.port

        timeout = Timeout(connect=SHORT_TIMEOUT, total=LONG_TIMEOUT)
        with HTTPConnectionPool(
            TARPIT_HOST, self.port, timeout=timeout, retries=False
        ) as pool:
            conn = pool._new_conn()
            with pytest.raises(ConnectTimeoutError):
                conn.connect(connect_timeout=timeout.connect_timeout)


class TestConnectionPool(HTTPDummyServerTestCase):
    def setup_method(self, method):
        self.pool = HTTPConnectionPool(self.host, self.port)

    def teardown_method(self):
        self.pool.close()

    def test_get(self):
        r = self.pool.request("GET", "/specific_method", fields={"method": "GET"})
        assert r.status_code == 200, r.data

    def test_post_url(self):
        r = self.pool.request("POST", "/specific_method", fields={"method": "POST"})
        assert r.status_code == 200, r.data

    def test_urlopen_put(self):
        r = self.pool.urlopen("PUT", "/specific_method?method=PUT")
        assert r.status_code == 200, r.data

    def test_wrong_specific_method(self):
        # To make sure the dummy server is actually returning failed responses
        r = self.pool.request("GET", "/specific_method", fields={"method": "POST"})
        assert r.status_code == 400, r.data

        r = self.pool.request("POST", "/specific_method", fields={"method": "GET"})
        assert r.status_code == 400, r.data

    def test_upload(self):
        data = "I'm in ur multipart form-data, hazing a cheezburgr"
        fields = {
            "upload_param": "filefield",
            "upload_filename": "lolcat.txt",
            "upload_size": len(data),
            "filefield": ("lolcat.txt", data),
        }

        r = self.pool.request("POST", "/upload", fields=fields)
        assert r.status_code == 200, r.data

    def test_one_name_multiple_values(self):
        fields = [("foo", "a"), ("foo", "b")]

        # urlencode
        r = self.pool.request("GET", "/echo", fields=fields)
        assert r.data == b"foo=a&foo=b"

        # multipart
        r = self.pool.request("POST", "/echo", fields=fields)
        assert r.data.count(b'name="foo"') == 2

    def test_request_method_body(self):
        body = b"hi"
        r = self.pool.request("POST", "/echo", body=body)
        assert r.data == body

        fields = [("hi", "hello")]
        with pytest.raises(TypeError):
            self.pool.request("POST", "/echo", body=body, fields=fields)

    def test_unicode_upload(self):
        fieldname = u("myfile")
        filename = u("\xe2\x99\xa5.txt")
        data = u("\xe2\x99\xa5").encode("utf8")
        size = len(data)

        fields = {
            u("upload_param"): fieldname,
            u("upload_filename"): filename,
            u("upload_size"): size,
            fieldname: (filename, data),
        }

        r = self.pool.request("POST", "/upload", fields=fields)
        assert r.status_code == 200, r.data

    def test_nagle(self):
        """ Test that connections have TCP_NODELAY turned on """
        # This test needs to be here in order to be run. socket.create_connection actually tries
        # to connect to the host provided so we need a dummyserver to be running.
        with HTTPConnectionPool(self.host, self.port) as pool:
            try:
                conn = pool._get_conn()
                pool._make_request(conn, "GET", "/")
                tcp_nodelay_setting = conn._sock.getsockopt(
                    socket.IPPROTO_TCP, socket.TCP_NODELAY
                )
                assert tcp_nodelay_setting
            finally:
                conn.close()

    def test_socket_options(self):
        """Test that connections accept socket options."""
        # This test needs to be here in order to be run. socket.create_connection actually tries to
        # connect to the host provided so we need a dummyserver to be running.
        with HTTPConnectionPool(
            self.host,
            self.port,
            socket_options=[(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)],
        ) as pool:
            conn = pool._new_conn()
            conn.connect()
            s = conn._sock
            using_keepalive = s.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) > 0
            assert using_keepalive
            s.close()

    def test_disable_default_socket_options(self):
        """Test that passing None disables all socket options."""
        # This test needs to be here in order to be run. socket.create_connection actually tries
        # to connect to the host provided so we need a dummyserver to be running.
        with HTTPConnectionPool(self.host, self.port, socket_options=None) as pool:
            conn = pool._new_conn()
            conn.connect()
            s = conn._sock
            using_nagle = s.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) == 0
            assert using_nagle
            s.close()

    def test_defaults_are_applied(self):
        """Test that modifying the default socket options works."""
        # This test needs to be here in order to be run. socket.create_connection actually tries
        # to connect to the host provided so we need a dummyserver to be running.
        with HTTPConnectionPool(self.host, self.port) as pool:
            # Get the HTTPConnection instance
            conn = pool._new_conn()
            try:
                # Update the default socket options
                conn.default_socket_options += [
                    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                ]
                conn.connect()
                s = conn._sock
                nagle_disabled = (
                    s.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) > 0
                )
                using_keepalive = (
                    s.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) > 0
                )
                assert nagle_disabled
                assert using_keepalive
            finally:
                conn.close()
                s.close()

    def test_connection_error_retries(self):
        """ ECONNREFUSED error should raise a connection error, with retries """
        port = find_unused_port()
        with HTTPConnectionPool(self.host, port) as pool:
            with pytest.raises(MaxRetryError) as e:
                pool.request("GET", "/", retries=Retry(connect=3))
            assert type(e.value.reason) == NewConnectionError

    def test_timeout_success(self):
        timeout = Timeout(connect=3, read=5, total=None)
        with HTTPConnectionPool(self.host, self.port, timeout=timeout) as pool:
            pool.request("GET", "/")
            # This should not raise a "Timeout already started" error
            pool.request("GET", "/")

        with HTTPConnectionPool(self.host, self.port, timeout=timeout) as pool:
            # This should also not raise a "Timeout already started" error
            pool.request("GET", "/")

        timeout = Timeout(total=None)
        with HTTPConnectionPool(self.host, self.port, timeout=timeout) as pool:
            pool.request("GET", "/")

    def test_bad_connect(self):
        with HTTPConnectionPool("badhost.invalid", self.port) as pool:
            with pytest.raises(MaxRetryError) as e:
                pool.request("GET", "/", retries=5)
            assert type(e.value.reason) == NewConnectionError

    def test_keepalive(self):
        with HTTPConnectionPool(self.host, self.port, block=True, maxsize=1) as pool:
            r = pool.request("GET", "/keepalive?close=0")
            r = pool.request("GET", "/keepalive?close=0")

            assert r.status_code == 200
            assert pool.num_connections == 1
            assert pool.num_requests == 2

    def test_keepalive_close(self):
        with HTTPConnectionPool(
            self.host, self.port, block=True, maxsize=1, timeout=2
        ) as pool:
            r = pool.request(
                "GET", "/keepalive?close=1", retries=0, headers={"Connection": "close"}
            )

            assert pool.num_connections == 1

            # The dummyserver will have responded with Connection:close,
            # and httplib will properly cleanup the socket.

            # We grab the HTTPConnection object straight from the Queue,
            # because _get_conn() is where the check & reset occurs
            # pylint: disable-msg=W0212
            conn = pool.pool.get()
            assert conn._sock is None
            pool._put_conn(conn)

            # Now with keep-alive
            r = pool.request(
                "GET",
                "/keepalive?close=0",
                retries=0,
                headers={"Connection": "keep-alive"},
            )

            # The dummyserver responded with Connection:keep-alive, the connection
            # persists.
            conn = pool.pool.get()
            assert conn._sock is not None
            pool._put_conn(conn)

            # Another request asking the server to close the connection. This one
            # should get cleaned up for the next request.
            r = pool.request(
                "GET", "/keepalive?close=1", retries=0, headers={"Connection": "close"}
            )

            assert r.status_code == 200

            conn = pool.pool.get()
            assert conn._sock is None
            pool._put_conn(conn)

            # Next request
            r = pool.request("GET", "/keepalive?close=0")

    def test_post_with_urlencode(self):
        data = {"banana": "hammock", "lol": "cat"}
        r = self.pool.request("POST", "/echo", fields=data, encode_multipart=False)
        assert r.data.decode("utf-8") == urlencode(data)

    def test_post_with_multipart(self):
        data = {"banana": "hammock", "lol": "cat"}
        r = self.pool.request("POST", "/echo", fields=data, encode_multipart=True)
        body = r.data.split(b"\r\n")

        encoded_data = encode_multipart_formdata(data)[0]
        expected_body = encoded_data.split(b"\r\n")

        # TODO: Get rid of extra parsing stuff when you can specify
        # a custom boundary to encode_multipart_formdata
        """
        We need to loop the return lines because a timestamp is attached
        from within encode_multipart_formdata. When the server echos back
        the data, it has the timestamp from when the data was encoded, which
        is not equivalent to when we run encode_multipart_formdata on
        the data again.
        """
        for i, line in enumerate(body):
            if line.startswith(b"--"):
                continue

            assert body[i] == expected_body[i]

    def test_post_with_multipart__iter__(self):
        data = {"hello": "world"}
        r = self.pool.request(
            "POST",
            "/echo",
            fields=data,
            preload_content=False,
            multipart_boundary="boundary",
            encode_multipart=True,
        )

        chunks = [chunk for chunk in r]
        assert chunks == [
            b"--boundary\r\n",
            b'Content-Disposition: form-data; name="hello"\r\n',
            b"\r\n",
            b"world\r\n",
            b"--boundary--\r\n",
        ]

    def test_check_gzip(self):
        r = self.pool.request(
            "GET", "/encodingrequest", headers={"accept-encoding": "gzip"}
        )
        assert r.headers.get("content-encoding") == "gzip"
        assert r.data == b"hello, world!"

    def test_check_deflate(self):
        r = self.pool.request(
            "GET", "/encodingrequest", headers={"accept-encoding": "deflate"}
        )
        assert r.headers.get("content-encoding") == "deflate"
        assert r.data == b"hello, world!"

    def test_bad_decode(self):
        with pytest.raises(DecodeError):
            self.pool.request(
                "GET",
                "/encodingrequest",
                headers={"accept-encoding": "garbage-deflate"},
            )

        with pytest.raises(DecodeError):
            self.pool.request(
                "GET", "/encodingrequest", headers={"accept-encoding": "garbage-gzip"}
            )

    def test_connection_count(self):
        with HTTPConnectionPool(self.host, self.port, maxsize=1) as pool:
            pool.request("GET", "/")
            pool.request("GET", "/")
            pool.request("GET", "/")

            assert pool.num_connections == 1
            assert pool.num_requests == 3

    def test_connection_count_bigpool(self):
        with HTTPConnectionPool(self.host, self.port, maxsize=16) as http_pool:
            http_pool.request("GET", "/")
            http_pool.request("GET", "/")
            http_pool.request("GET", "/")

            assert http_pool.num_connections == 1
            assert http_pool.num_requests == 3

    def test_partial_response(self):
        with HTTPConnectionPool(self.host, self.port, maxsize=1) as pool:
            req_data = {"lol": "cat"}
            resp_data = urlencode(req_data).encode("utf-8")

            r = pool.request("GET", "/echo", fields=req_data, preload_content=False)

            assert r.read(5) == resp_data[:5]
            assert r.read() == resp_data[5:]

    def test_lazy_load_twice(self):
        # This test is sad and confusing. Need to figure out what's
        # going on with partial reads and socket reuse.

        with HTTPConnectionPool(
            self.host, self.port, block=True, maxsize=1, timeout=2
        ) as pool:
            payload_size = 1024 * 2
            first_chunk = 512

            boundary = "foo"

            req_data = {"count": "a" * payload_size}
            resp_data = encode_multipart_formdata(req_data, boundary=boundary)[0]

            req2_data = {"count": "b" * payload_size}
            resp2_data = encode_multipart_formdata(req2_data, boundary=boundary)[0]

            r1 = pool.request(
                "POST",
                "/echo",
                fields=req_data,
                multipart_boundary=boundary,
                preload_content=False,
            )

            first_data = r1.read(first_chunk)
            assert len(first_data) > 0
            assert first_data == resp_data[: len(first_data)]

            try:
                r2 = pool.request(
                    "POST",
                    "/echo",
                    fields=req2_data,
                    multipart_boundary=boundary,
                    preload_content=False,
                    pool_timeout=0.001,
                )

                # This branch should generally bail here, but maybe someday it will
                # work? Perhaps by some sort of magic. Consider it a TODO.

                second_data = r2.read(first_chunk)
                assert len(second_data) > 0
                assert second_data == resp2_data[: len(second_data)]

                assert r1.read() == resp_data[len(first_data) :]
                assert r2.read() == resp2_data[len(second_data) :]
                assert pool.num_requests == 2

            except EmptyPoolError:
                assert r1.read() == resp_data[len(first_data) :]
                assert pool.num_requests == 1

            assert pool.num_connections == 1

    def test_for_double_release(self):
        MAXSIZE = 5

        # Check default state
        with HTTPConnectionPool(self.host, self.port, maxsize=MAXSIZE) as pool:
            assert pool.num_connections == 0
            assert pool.pool.qsize() == MAXSIZE

            # Make an empty slot for testing
            pool.pool.get()
            assert pool.pool.qsize() == MAXSIZE - 1

            # Check state after simple request
            pool.urlopen("GET", "/")
            assert pool.pool.qsize() == MAXSIZE - 1

            # Check state without release
            pool.urlopen("GET", "/", preload_content=False)
            assert pool.pool.qsize() == MAXSIZE - 2

            pool.urlopen("GET", "/")
            assert pool.pool.qsize() == MAXSIZE - 2

            # Check state after read
            pool.urlopen("GET", "/").data
            assert pool.pool.qsize() == MAXSIZE - 2

            pool.urlopen("GET", "/")
            assert pool.pool.qsize() == MAXSIZE - 2

    def test_connections_arent_released(self):
        MAXSIZE = 5
        with HTTPConnectionPool(self.host, self.port, maxsize=MAXSIZE) as pool:
            assert pool.pool.qsize() == MAXSIZE

            pool.request("GET", "/", preload_content=False)
            assert pool.pool.qsize() == MAXSIZE - 1

    def test_dns_error(self):
        pool = HTTPConnectionPool(
            "thishostdoesnotexist.invalid", self.port, timeout=0.001
        )
        with pytest.raises(MaxRetryError):
            pool.request("GET", "/test", retries=2)

    def test_percent_encode_invalid_target_chars(self):
        with HTTPConnectionPool(self.host, self.port) as pool:
            r = pool.request("GET", "/echo_params?q=\r&k=\n \n")
            assert r.data == b"[('k', '\\n \\n'), ('q', '\\r')]"

    def test_source_address(self):
        for addr, is_ipv6 in VALID_SOURCE_ADDRESSES:
            if is_ipv6 and not HAS_IPV6_AND_DNS:
                warnings.warn("No IPv6 support: skipping.", NoIPv6Warning)
                continue
            with HTTPConnectionPool(
                self.host, self.port, source_address=addr, retries=False
            ) as pool:
                r = pool.request("GET", "/source_address")
                assert r.data == b(addr[0])

    def test_source_address_error(self):
        for addr in INVALID_SOURCE_ADDRESSES:
            with HTTPConnectionPool(
                self.host, self.port, source_address=addr, retries=False
            ) as pool:
                with pytest.raises(NewConnectionError):
                    pool.request("GET", "/source_address?{0}".format(addr))

    def test_stream_keepalive(self):
        x = 2

        for _ in range(x):
            response = self.pool.request(
                "GET",
                "/chunked",
                headers={"Connection": "keep-alive"},
                preload_content=False,
                retries=False,
            )
            for chunk in response.stream(3):
                assert chunk == b"123"

        assert self.pool.num_connections == 1
        assert self.pool.num_requests == x

    def test_chunked_gzip(self):
        response = self.pool.request(
            "GET", "/chunked_gzip", preload_content=False, decode_content=True
        )

        assert b"123" * 4 == response.read()

    def test_mixed_case_hostname(self):
        with HTTPConnectionPool("LoCaLhOsT", self.port) as pool:
            response = pool.request("GET", "http://LoCaLhOsT:%d/" % self.port)
            assert response.status_code == 200
