import typing

class Origin:
    def __init__(self, scheme: str, host: str, port: int):
        self.scheme = scheme
        self.host = host
        self.port = port

class URL:
    def __init__(
        self,
        url: str = None,
        scheme: str = None,
        username: str = None,
        password: str = None,
        host: str = None,
        port: int = None,
        path: str = None,
        query: typing.Union[str, typing.Mapping[str, str]] = None,
        fragment: str = None,
    ): ...  # TODO: Implement the URL interface
    @property
    def origin(self) -> Origin: ...
