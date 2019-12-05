import trio
import h11
import typing
from hip.models import Request, Response, AsyncResponse
from hip._backends import AsyncSocket, AbortSendAndReceive


class HTTPTransaction:
    def __init__(self, socket: AsyncSocket):
        self.socket = socket

    async def send_request(
        self, request: Request, request_data: typing.AsyncIterator[bytes]
    ) -> AsyncResponse:
        """Starts an HTTP request and sends request data (if any) while waiting
        for an HTTP response to be received. Exits upon receiving an HTTP response.
        """

    async def receive_response_data(
        self, request_data: typing.AsyncIterator[bytes]
    ) -> typing.AsyncIterable[bytes]:
        """Continues sending HTTP request data (if any) while streaming HTTP response data"""

    async def close(self) -> None:
        """Readies the transport to be used for a different HTTP transaction if possible."""


class HTTP11Transaction(HTTPTransaction):
    def __init__(self, socket: AsyncSocket):
        super().__init__(socket)

        self.h11 = h11.Connection(h11.CLIENT)

    async def send_request(
        self, request: Request, request_data: typing.AsyncIterator[bytes]
    ) -> AsyncResponse:
        h11_request = _request_to_h11_event(request)
        await self.socket.send_all(self.h11.send(h11_request))

        response_history: typing.List[Response] = []
        response: typing.Optional[AsyncResponse] = None
        expect_100 = request.headers.get("expect", "") == "100-continue"
        expect_100_event = trio.Event()

        async def produce_bytes() -> typing.Optional[bytes]:
            nonlocal expect_100
            # Don't start sending until we receive back any response.
            if expect_100:
                await expect_100_event.wait()
                expect_100 = False
            try:
                nonlocal request_data
                data = await _iter_next(request_data)
                data_to_send = self.h11.send(h11.Data(data=data))
                return data_to_send
            except StopAsyncIteration:
                return None

        def consume_bytes(data: bytes) -> None:
            nonlocal response, expect_100
            self.h11.receive_data(data)
            event = self.h11.next_event()
            while event is not h11.NEED_DATA:
                if isinstance(event, h11.InformationalResponse):
                    if expect_100 and event.status_code == 100:
                        expect_100_event.set()
                    response_history.append(
                        Response(
                            status_code=event.status_code,
                            headers=event.headers,
                            http_version=f"HTTP/{event.http_version.decode()}",
                        )
                    )

                elif isinstance(event, h11.Response):
                    response = AsyncResponse(
                        status_code=event.status_code,
                        headers=event.headers,
                        http_version=f"HTTP/{event.http_version.decode()}",
                        request=request,
                        raw_data=self.receive_response_data(request_data).__aiter__(),
                    )
                    response.history = response_history
                    raise AbortSendAndReceive()
                else:
                    raise ValueError(str(event))

                event = self.h11.next_event()

        await self.socket.send_and_receive_for_a_while(
            produce_bytes, consume_bytes, 10.0
        )
        return response

    async def receive_response_data(
        self, request_data: typing.AsyncIterator[bytes]
    ) -> typing.AsyncIterable[bytes]:

        request_data_empty = False
        response_data: typing.List[bytes] = []
        response_ended = False

        def process_response_data() -> None:
            nonlocal response_ended, response_data
            event = self.h11.next_event()
            while event is not h11.NEED_DATA:
                if isinstance(event, h11.Data):
                    response_data.append(event.data)
                elif isinstance(event, h11.EndOfMessage):
                    response_ended = True
                else:
                    raise ValueError(str(event))
                event = self.h11.next_event()

            if response_data:
                raise AbortSendAndReceive()

        def get_response_data() -> bytes:
            nonlocal response_data
            data = b"".join(response_data)
            response_data = []
            return data

        # Start off by parsing all events remaining in the
        # pipeline from .send_request() for response data.
        try:
            process_response_data()
        except AbortSendAndReceive:
            yield get_response_data()

        async def produce_bytes() -> typing.Optional[bytes]:
            nonlocal request_data_empty

            if request_data_empty:
                return None
            try:
                data = await _iter_next(request_data)
                return self.h11.send(h11.Data(data=data))
            except StopAsyncIteration:
                request_data_empty = True
                return self.h11.send(h11.EndOfMessage()) or None

        def consume_bytes(data: bytes) -> None:
            self.h11.receive_data(data)
            process_response_data()

        while not response_ended:
            try:
                await self.socket.send_and_receive_for_a_while(
                    produce_bytes, consume_bytes, 10.0
                )
            except AbortSendAndReceive:
                yield get_response_data()

    async def close(self) -> None:
        ...


def _request_to_h11_event(request: Request) -> h11.Request:
    # Put the 'Host' header first in the request as it's required.
    h11_headers = [(b"host", request.headers["host"].encode())]
    for k, v in request.headers.items():
        if k.lower() != "host":
            h11_headers.append((k.encode(), v.encode()))
    return h11.Request(
        method=request.method.encode(),
        target=request.target.encode(),
        headers=h11_headers,
    )


T = typing.TypeVar("T")


async def _iter_next(iterator: typing.AsyncIterator[T]) -> T:
    return await iterator.__anext__()
