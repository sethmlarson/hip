import typing

Request = typing.Any
Response = typing.Any

class Retry:
    """Both a configuration object for retries and the
    data-class that mutates as a Session attempts to
    complete a single request. A single 'Retry' object
    spans multiple
    """

    DEFAULT_RETRYABLE_METHODS = frozenset(
        ("HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE",)
    )
    DEFAULT_RETRY_AFTER_STATUS_CODES = frozenset((413, 429, 503))
    def __init__(
        self,
        # Number of total retries allowed.
        total_retries: typing.Optional[int] = None,
        *,
        # Number of retries allows for individual categories
        connect_retries: typing.Optional[int] = None,
        read_retries: typing.Optional[int] = None,
        response_retries: typing.Optional[int] = None,
        # Methods which are allowed to be retried (idempotent).
        retryable_methods: typing.Collection[str] = DEFAULT_RETRYABLE_METHODS,
        # Status codes that must be retried.
        retryable_status_codes: typing.Collection[int] = (),
        # Set a maximum value for 'Retry-After' where we send the request anyways.
        max_retry_after: typing.Optional[float] = 30.0,
        # Back-offs to not overwhelm a service experiencing
        # temporary errors and give time to recover.
        backoff_factor: float = 0.0,
        backoff_jitter: float = 0.0,
        max_backoff: typing.Optional[float] = 0.0,
        # Number of total times a request has been retried before
        # receiving a non-error response (less than 400) or received
        # a retryable error / timeout. This value gets reset to 0 by
        # .performed_http_redirect().
        _back_to_back_errors: int = 0,
    ): ...
    def should_retry(
        self, request: Request, response: Response
    ) -> typing.Optional[Request]:
        """Returns whether the Request should be retried at all.
        Allows for rewriting the Request for sub-classes but currently
        just returns the Request that's been passed in.

        If the Request shouldn't be retried return 'None'.
        """
    def delay_before_next_request(self, request: Request, response: Response) -> float:
        """Returns the delay in seconds between issuing the next request
        This interface combines backoff and 'Retry-After' headers into one.
        """
    def performed_http_redirect(self) -> "Retry":
        """Callback that signals to the 'Retry' instance that an HTTP
        redirect was performed and the '_back_to_back_errors' counter
        should be reset to 0 so that back-offs don't continue to grow
        after a service successfully processes our request.

        This callback shouldn't be called when a redirect is returned
        by to the caller, because it's basically a no-op in that case.
        """
    def increment(
        self,
        *,
        connect: bool = False,
        read: bool = False,
        response: typing.Optional[Response] = None,
        error: typing.Optional[Exception] = None,
    ) -> "Retry":
        """Increments the Retry instance down by the given values.
        """
    def copy(self) -> "Retry":
        """Creates a new instance of the current 'Retry' object. This is used
        by the 'Session' object to not modify the Session object's instance
        used for configuration.
        """
