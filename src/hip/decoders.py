"""Decoders for all Accept-Encoding headers"""
import enum
import typing
import functools
import zlib
import types

brotli: typing.Optional[types.ModuleType]
zstandard: typing.Optional[types.ModuleType]
try:
    import brotli
except ImportError:
    brotli = None

try:
    import zstandard
except ImportError:
    zstandard = None


class Decoder:
    def decompress(self, data: bytes) -> bytes:
        raise NotImplementedError()

    def flush(self) -> bytes:
        raise NotImplementedError()


class IdentityDecoder(Decoder):
    def decompress(self, data: bytes) -> bytes:
        return data

    def flush(self) -> bytes:
        return b""


class DeflateDecoder(Decoder):
    def __init__(self) -> None:
        self._first_try = True
        self._data = bytearray()
        self._obj = zlib.decompressobj()

    def decompress(self, data: bytes) -> bytes:
        if not data:
            return data

        if not self._first_try:
            return self._obj.decompress(data)

        self._data += data
        try:
            decompressed = self._obj.decompress(data)
            if decompressed:
                self._first_try = False
                self._data = bytearray()
            return decompressed
        except zlib.error:
            self._first_try = False
            self._obj = zlib.decompressobj(-zlib.MAX_WBITS)
            data = bytes(self._data)
            self._data = bytearray()
            return self.decompress(data)

    def flush(self) -> bytes:
        return self._obj.flush()


class GzipDecoderState(enum.Enum):
    FIRST_MEMBER = 0
    OTHER_MEMBERS = 1
    SWALLOW_DATA = 2


class GzipDecoder(Decoder):
    def __init__(self) -> None:
        self._obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self._state = GzipDecoderState.FIRST_MEMBER

    def decompress(self, data: bytes) -> bytes:
        ret = bytearray()
        if self._state == GzipDecoderState.SWALLOW_DATA or not data:
            return bytes(ret)
        while True:
            try:
                ret += self._obj.decompress(data)
            except zlib.error:
                previous_state = self._state
                # Ignore data after the first error
                self._state = GzipDecoderState.SWALLOW_DATA
                if previous_state == GzipDecoderState.OTHER_MEMBERS:
                    # Allow trailing garbage acceptable in other gzip clients
                    return bytes(ret)
                raise
            data = self._obj.unused_data
            if not data:
                return bytes(ret)
            self._state = GzipDecoderState.OTHER_MEMBERS
            self._obj = zlib.decompressobj(16 + zlib.MAX_WBITS)

    def flush(self) -> bytes:
        return self._obj.flush()


if brotli is not None:

    class BrotliDecoder(Decoder):
        """Supports both 'brotlipy' and 'Brotli' packages
        since they share a top-level import name. The top
        code branches support 'brotlipy' and the bottom
        code branches support 'Brotli'.
        """

        def __init__(self) -> None:
            self._obj = brotli.Decompressor()

        def decompress(self, data: bytes) -> bytes:
            try:
                return self._obj.decompress(data)
            except AttributeError:
                return self._obj.process(data)

        def flush(self) -> bytes:
            try:
                return self._obj.flush()
            except AttributeError:
                return b""


if zstandard is not None:

    class ZstdDecoder(Decoder):
        """RFC 8478 currently in use by Facebook mostly"""

        def __init__(self) -> None:
            self._decompressor = zstandard.ZstdDecompressor()
            self._obj = self._decompressor.decompressobj()

        def decompress(self, data: bytes) -> bytes:
            return self._obj.decompress(data)

        def flush(self) -> bytes:
            return self._obj.flush() or b""


class MultiDecoder(Decoder):
    """
    From RFC7231:
        If one or more encodings have been applied to a representation, the
        sender that applied the encodings MUST generate a Content-Encoding
        header field that lists the content codings in the order in which
        they were applied.
    """

    def __init__(self, content_encoding: str) -> None:
        self._decompressors = [
            get_content_decoder(m.strip()) for m in content_encoding.split(",")
        ][::-1]

    def decompress(self, data: bytes) -> bytes:
        for d in self._decompressors:
            data = d.decompress(data)
        return data

    def flush(self) -> bytes:
        return self._decompressors[-1].flush()


def get_content_decoder(content_encoding: str) -> Decoder:
    content_encoding = content_encoding.strip()
    if "," in content_encoding:
        return MultiDecoder(content_encoding)
    if content_encoding in ("gzip", "x-gzip"):
        return GzipDecoder()
    if content_encoding in ("deflate", "x-deflate"):
        return DeflateDecoder()
    if brotli is not None and content_encoding == "br":
        return BrotliDecoder()
    if zstandard is not None and content_encoding == "zstd":
        return ZstdDecoder()
    # Give up, we don't know what this Content-Encoding is.
    return IdentityDecoder()


@functools.lru_cache(1)
def accept_encoding() -> str:
    """Returns the value of 'Accept-Encoding' that the client should use.
    This value varies depending on what packages are installed.
    """
    accept_enc = ["gzip", "deflate"]
    if brotli is not None:
        accept_enc.append("br")
    if zstandard is not None:
        accept_enc.append("zstd")
    return ", ".join(accept_enc)
