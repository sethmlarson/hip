import base64
import typing
from hip.models import Request
from hip.utils import to_bytes


class BasicAuth:
    """Implements RFC 7617 - Basic Authentication"""

    def __init__(
        self,
        username: typing.Union[str, bytes],
        password: typing.Union[str, bytes],
        *,
        encoding="latin-1",
    ):
        username = to_bytes(username, encoding=encoding)
        password = to_bytes(password, encoding=encoding)

        self._header = (
            f"Basic {base64.b64encode(b'%b:%b' % (username, password)).decode()}"
        )

    def __call__(self, request: Request) -> Request:
        request.headers.setdefault("authorization", self._header)
        return request
