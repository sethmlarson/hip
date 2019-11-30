import typing
from ..models import Request, Response, Headers
from ..structures import ConnectionConfig


class HTTPLifecycle:
    """Represents a single HTTP Request -> Response over some transport.
    The transport is abstracted away and only known to the 'ConnectionManager'.
    This lifecycle object is what the 'Session' objects see and use to send requests.

    Possible transports include:
    - HTTP/1.1
    - HTTP/1.1 proxied through HTTP/1.X
    - HTTP/2 stream
    - HTTP/2 proxied through HTTP/1.x
    - HTTP/3 over UDP
    """

    async def send_request_data(self, data: bytes) -> None:
        """Sends request data"""

    async def send_eof(self, trailers: typing.Optional[Headers] = None) -> None:
        """Signals that the request has finished sending and optionally sends trailers"""

    async def receive_response_headers(self) -> Response:
        """Waits for the first non-1XX response in the HTTP lifecycle. Saves
        all of the 1XX responses in the 'history' and returns them all
        as a 'Response' object without any body.
        """

    async def receive_response_data(self, max_nbytes: int) -> bytes:
        """Receives response data from the transport"""

    def get_response_trailers(self) -> typing.Optional[Headers]:
        """If trailers were sent after all response data was sent
        they will be populated here. If not all response data
        has been sent this function returns 'None'
        """

    async def close(self) -> None:
        """Marks the underlying transport as inactive"""


class ConnectionManager:
    async def start_http_lifecycle(
        self, request: Request, conn_config: ConnectionConfig
    ) -> HTTPLifecycle:
        ...
