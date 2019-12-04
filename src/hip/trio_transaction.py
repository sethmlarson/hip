import trio
import h11
import typing
from .models import Request, Response
from .trio_backend import TrioBackend, TrioSocket, LoopAbort


class HTTPTransaction:
    async def send_request(
        self, request: Request, request_data: typing.AsyncIterable[bytes]
    ) -> Response:
        ...

    async def receive_response_data(
        self, request_data: typing.AsyncIterable[bytes]
    ) -> typing.AsyncIterable[bytes]:
        ...

    async def close(self) -> None:
        ...


class HTTP11Transaction(HTTPTransaction):
    def __init__(self):
        self.h11 = h11.Connection(h11.CLIENT)
        self.trio_socket: typing.Optional[TrioSocket] = None

    async def send_request(
        self, request: Request, request_data: typing.AsyncIterable[bytes]
    ) -> Response:

        # TODO: This has to be managed externally from the HTTP transaction.
        trio_backend = TrioBackend()
        self.trio_socket = await trio_backend.connect(
            request.url.host, request.url.port, connect_timeout=10.0
        )

        # Construct an HTTP/1.1 Request
        h11_headers = [(b"host", request.headers["host"].encode())]
        for k, v in request.headers.items():
            if k.lower() != "host":
                h11_headers.append((k.encode(), v.encode()))
        h11_request = h11.Request(
            method=request.method.encode(),
            target=request.target.encode(),
            headers=h11_headers,
        )
        await self.trio_socket.send_all(self.h11.send(h11_request))

        request_data_empty = False
        response_history: typing.List[Response] = None
        response: typing.Optional[Response] = None
        expect_100 = request.headers.get("expect", "") == "100-continue"
        expect_100_event = trio.Event()

        async def produce_bytes() -> typing.Optional[bytes]:
            nonlocal request_data_empty
            if expect_100:
                await expect_100_event.wait()
            try:
                nonlocal request_data
                data = await request_data.__anext__()
                return self.h11.send(h11.Data(data=data))
            except StopAsyncIteration:
                if not request_data_empty:
                    request_data_empty = True
                    return self.h11.send(h11.EndOfMessage())
                else:
                    return None

        def consume_bytes(data: bytes) -> None:
            nonlocal response
            self.h11.receive_data(data)
            event = self.h11.next_event()
            while event is not h11.NEED_DATA:
                if isinstance(event, h11.InformationalResponse):
                    if event.status_code == 100 and expect_100:
                        expect_100_event.set()
                    response_history.append(_h11_event_to_response(event))

                elif isinstance(event, h11.Response):
                    response = _h11_event_to_response(event)
                    response.history = response_history
                    raise LoopAbort()
                else:
                    raise ValueError(str(event))

        await self.trio_socket.send_and_receive_for_a_while(
            produce_bytes, consume_bytes, 10.0
        )
        return response

    async def receive_response_data(
        self, request_data: typing.AsyncIterable[bytes]
    ) -> typing.AsyncIterable[bytes]:
        ...

    async def close(self) -> None:
        self.trio_socket.forceful_close()


def _h11_event_to_response(
    event: typing.Union[h11.InformationalResponse, h11.Response]
) -> Response:
    """Converts an h11.*Response event into hip.Response"""
    return Response(
        status_code=event.status_code,
        headers=event.headers,
        http_version=f"HTTP/{event.http_version.decode()}",
    )
