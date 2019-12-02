import typing

Origin = typing.Any
ParamsValueType = str
ParamsType = typing.Union[
    typing.Sequence[typing.Tuple[str, ParamsValueType]],
    typing.Mapping[str, typing.Optional[ParamsValueType]],
]
URLTypes = typing.Union[str, "URL"]

class URL:
    def __init__(
        self,
        url: typing.Optional[URLTypes] = None,
        *,
        scheme: typing.Optional[str] = None,
        username: typing.Optional[str] = None,
        password: typing.Optional[str] = None,
        host: typing.Optional[str] = None,
        port: typing.Optional[int] = None,
        path: typing.Optional[typing.Union[str, typing.Sequence[str]]] = None,
        params: typing.Optional[ParamsType] = None,
        fragment: typing.Optional[str] = None,
    ): ...
    @property
    def origin(self) -> Origin: ...
    def join(self, url: URLTypes) -> "URL": ...
