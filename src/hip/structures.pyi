import typing

class AltSvc(typing.NamedTuple):
    """Holds onto information found from the 'AltSvc' HTTP header.
    What's important to note is that even though we're connecting
    to a different host and port than the request origin we need
    to act as though we're still talking to the originally requested
    origin (in the 'Host' header, checking hostname on certificate, etc).
    """

    alpn_protocol: str
    host: str
    port: int
    expires_at: int
    @classmethod
    def from_header(cls, value: str) -> typing.List["AltSvc"]:
        """Parses the value of the 'AltSvc' header according to RFC 7838
        and returns a list of values.
        """

class HSTS(typing.NamedTuple):
    """Holds onto information about whether a given host should be only
    accessed via TLS. See RFC 6797. 'preload' isn't defined in the RFC
    but is used to signal that the website wishes to be in the HSTS preload
    list. We can potentially use this as a signal that the website doesn't
    want to expire ever? Also the 'preload' flag is set if this 'HSTS'
    instance was grabbed from a static HSTS preload list.
    """

    host: str
    include_subdomains: bool
    expires_at: typing.Optional[int]
    preload: bool
    @classmethod
    def from_header(cls, value: str) -> "HSTS":
        """Parses the value of the 'Strict-Transport-Security' header."""

class RequestCacheControl(typing.NamedTuple):
    """A parsed 'Cache-Control' header from a request.
    Requests support the following directives: max-age, max-stale,
    min-fresh, no-cache, no-store, no-transform, only-if-cached.

    For cache-control structures 'None' means not present, 'True'
    means that the directive was present but without a d=[x] value,
    and an integer/string means that there was a value for that
    directive.  All directives that aren't understood within
    the context are added within 'other_directives' but are not
    used by the client library to make decisions.
    """

    max_age: typing.Optional[int]
    max_stale: typing.Optional[typing.Union[typing.Literal[True], int]]
    min_fresh: typing.Optional[int]
    no_cache: typing.Optional[typing.Literal[True]]
    no_store: typing.Optional[typing.Literal[True]]
    no_transform: typing.Optional[typing.Literal[True]]
    only_if_cached: typing.Optional[typing.Literal[True]]

    other_directives: typing.Tuple[str, ...]
    @classmethod
    def from_header(cls, value: str) -> "RequestCacheControl":
        """Parses the value of 'Cache-Control' from a request headers."""

class ResponseCacheControl(typing.NamedTuple):
    """A parsed 'Cache-Control' header from a response.
    Responses support the following directives: must-revalidate,
    no-cache, no-store, no-transform, public, private, proxy-revalidate,
    max-age, s-maxage, immutable, stale-while-revalidated, stale-if-error
    """

    must_revalidate: typing.Optional[typing.Literal[True]]
    no_cache: typing.Optional[typing.Literal[True]]
    no_store: typing.Optional[typing.Literal[True]]
    no_transform: typing.Optional[typing.Literal[True]]
    public: typing.Optional[typing.Literal[True]]
    private: typing.Optional[typing.Literal[True]]
    proxy_revalidate: typing.Optional[typing.Literal[True]]
    max_age: typing.Optional[typing.Literal[True]]
    s_maxage: typing.Optional[typing.Literal[True]]
    immutable: typing.Optional[typing.Literal[True]]
    stale_while_revalidate: typing.Optional[int]
    stale_if_error: typing.Optional[int]

    other_directives: typing.Tuple[str, ...]
    @classmethod
    def from_header(cls, value: str) -> "ResponseCacheControl":
        """Parses the value of 'Cache-Control' from a response headers."""
