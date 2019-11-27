import os
import ssl
import pathlib
import typing
from ..models import URL, Origin
from ..structures import AltSvc, HSTS

class SessionStore:
    """This is the interface for the storage of information
    that a session needs to remember outside the scope of
    a single HTTP lifecycle. Here's a list of information that
    is stored within a 'SessionStore' along with it's corresponding key:

    - Cookies ('cookies')
    - AltSvc ('altsvc')
    - Permanent Redirects ('redirect')
    - HSTS ('hsts')
    - TLS Session Tickets ('tls_session_tickets')
    - Cached responses ('responses')

    Cached response bodies have the chance of being quite large so
    shouldn't be cached if the session store isn't writing to disk.
    This means that session stores that don't write to disk can
    choose not to implement response caching.
    """

    async def get_altsvc(self, origin: Origin) -> typing.List[AltSvc]:
        """Gets a list of 'AltSvc' for the origin"""
    async def get_cookies(
        self, origin: Origin,
    ) -> typing.Any:  # TODO: Replace with 'Cookies' type when implemented
        """Gets a collection of cookies that should be sent for all requests to the Origin"""
    async def get_redirects(self, url: URL) -> typing.Optional[URL]:
        """Gets a permanent redirect for the given URL if one has been received"""
    async def get_hsts(self, origin: Origin) -> typing.Optional[HSTS]:
        """Determines if the origin should only be accessed over TLS by
        comparing the host to a preloaded list of domains or if the
        'Strict-Transport-Security' header was sent on a previous response.
        """
    async def get_tls_session_tickets(
        self, origin: Origin
    ) -> typing.Optional[ssl.SSLSession]:
        """Loads any 'ssl.SSLSession' instances for a given Origin in order
        to resume TLS for a faster handshake.  Using session resumption only works
        for TLSv1.2 for now but that's a large chunk of TLS usage right now so still
        worth implementing.

        Somehow the SSLSession will have to be routed down to the low-level socket
        creation stage because SSLSocket.session must be set before calling do_handshake().
        """
    async def get_response(
        self, request: typing.Any
    ) -> typing.Optional[
        typing.Any
    ]:  # TODO: Replace with 'Response' type when implemented.
        """Looks for a response in the cache for the given request.
        This will need to parse the 'Cache-Control' header and look at
        extensions to see if the Request actually wants us to look in
        the cache.
        """
    async def clear(self, origin: Origin, keys: typing.Collection[str] = None) -> None:
        """Clears data from the session store.
        If given an Origin without a key then will clear all information for that key.
        If given an Origin and keys then only that information at those keys will
        be cleared.

        Session stores should take care that data is actually deleted
        all the way down, so if data is stored on disk the files should
        at least be scheduled for deletion.
        """

class MemorySessionStore(SessionStore):
    """This is a session store implementation that uses memory
    to hold on to information but never writes info to disk
    or stores it persistently.  This means that once the
    program terminates all session store information will
    be lost.

    This is the default session store type if no other
    session store is specified.
    """

class FilesystemSessionStore(SessionStore):
    """A session store that persists data stored onto the disk"""

    def __init__(self, path: typing.Union[str, pathlib.Path]): ...

class EmptySessionStore(SessionStore):
    """This is a session store that drops everything that's handed to it."""

def arg_to_session_store(
    session_store: typing.Union[None, str, pathlib.Path, "SessionStore"]
) -> SessionStore:
    """Converts a value passed to 'session_store' on a Session into
    a 'SessionStore' object. This allows users to specify ':memory:'
    or a 'pathlib.Path' object to use instead of having to construct
    the 'SessionStore' object manually.
    """
    if session_store is None:
        return EmptySessionStore()
    elif session_store == ":memory:":
        return MemorySessionStore()
    elif isinstance(session_store, (str, pathlib.Path)) and os.path.isdir(session_store):
        return FilesystemSessionStore(session_store)
    elif isinstance(session_store, SessionStore):
        return session_store
    raise ValueError("not a session store!")
