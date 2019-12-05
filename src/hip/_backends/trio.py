import trio
import typing
import socket
from .base import AsyncBackend, AsyncSocket, AbortSendAndReceive, is_readable
from hip import utils


# XX support connect_timeout and read_timeout


class TrioBackend(AsyncBackend):
    async def connect(
        self,
        host,
        port,
        *,
        connect_timeout,
        source_address: typing.Optional[typing.Tuple[str, int]] = None,
        socket_options=None
    ) -> "TrioSocket":
        if source_address is not None:
            # You can't really combine source_address= and happy eyeballs
            # (can we get rid of source_address? or at least make it a source
            # ip, no port?)
            raise NotImplementedError(
                "trio backend doesn't support setting source_address"
            )

        stream = await trio.open_tcp_stream(host, port)
        for (level, optname, value) in socket_options or ():
            stream.setsockopt(level, optname, value)

        return TrioSocket(stream)


# XX it turns out that we don't need SSLStream to be robustified against
# cancellation, but we probably should do something to detect when the stream
# has been broken by cancellation (e.g. a timeout) and make is_readable return
# True so the connection won't be reused.


class TrioSocket(AsyncSocket):
    def __init__(self, stream: typing.Union[trio.SocketStream, trio.SSLStream]):
        self._stream = stream

    async def start_tls(self, server_hostname, ssl_context):
        wrapped = trio.SSLStream(
            self._stream,
            ssl_context,
            server_hostname=server_hostname,
            https_compatible=True,
        )
        return TrioSocket(wrapped)

    def getpeercert(self, binary_form=False):
        return self._stream.getpeercert(binary_form=binary_form)

    async def send_all(self, data: bytes) -> None:
        await self._stream.send_all(data)

    async def receive_some(self) -> bytes:
        return await self._stream.receive_some(utils.CHUNK_SIZE)

    async def send_and_receive_for_a_while(
        self, produce_bytes, consume_bytes, read_timeout
    ):
        async def sender():
            while True:
                outgoing = await produce_bytes()
                if outgoing is None:
                    break
                await self._stream.send_all(outgoing)

        async def receiver():
            while True:
                incoming = await self._stream.receive_some(utils.CHUNK_SIZE)
                consume_bytes(incoming)

        try:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(sender)
                nursery.start_soon(receiver)
        except AbortSendAndReceive:
            pass

    # We want this to be synchronous, and don't care about graceful teardown
    # of the SSL/TLS layer.
    def forceful_close(self) -> None:
        self._socket().close()

    def is_readable(self) -> bool:
        return is_readable(self._socket())

    # Pull out the underlying trio socket, because it turns out HTTP is not so
    # great at respecting abstraction boundaries.
    def _socket(self) -> socket.socket:
        stream = self._stream
        # Strip off any layers of SSLStream
        while hasattr(stream, "transport_stream"):
            stream = stream.transport_stream
        # Now we have a SocketStream
        return stream.socket
