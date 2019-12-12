import codecs
import typing
import functools
import chardet
import binascii

CHUNK_SIZE = 65536


def _int_to_urlenc() -> typing.Dict[int, bytes]:
    """Creates a mapping of ordinals to bytes encoded via url-encoding"""
    values = {}
    special = {0x2A, 0x2D, 0x2E, 0x5F}
    for byte in range(256):
        if (
            (0x61 <= byte <= 0x7A)
            or (0x030 <= byte <= 0x5A and byte != 0x40)
            or (byte in special)
        ):  # Keep the ASCII
            values[byte] = bytes((byte,))
        elif byte == 0x020:  # Space -> '+'
            values[byte] = b"+"
        else:  # Percent-encoded
            values[byte] = b"%" + hex(byte)[2:].upper().encode()
    return values


INT_TO_URLENC = _int_to_urlenc()
INT_TO_HEX: typing.Dict[int, str] = {x: hex(x)[2:].upper().zfill(2) for x in range(256)}


class MimeType(typing.NamedTuple):
    type: str
    subtype: str
    suffix: str
    parameters: typing.Dict[str, typing.Optional[str]]

    def __hash__(self) -> int:
        return hash(
            (self.type, self.subtype, self.suffix, sorted(self.parameters.items()))
        )

    def __str__(self) -> str:
        """Renders the mime type without parameters"""
        if not self.type:
            return ""
        return (
            f"{self.type}"
            f"{'/' + self.subtype if self.subtype else ''}"
            f"{'+' + self.suffix if self.suffix else ''}"
        )


def parse_mimetype(mimetype: str) -> MimeType:
    if not mimetype:
        return MimeType(type="", subtype="", suffix="", parameters={})

    parts = mimetype.split(";")
    params = {}
    for item in parts[1:]:
        if not item:
            continue
        key, value = typing.cast(
            typing.Tuple[str, typing.Optional[str]],
            item.split("=", 1) if "=" in item else (item, None),
        )
        params[key.lower().strip()] = value.strip(' "') if value else value

    mimetype_no_params = parts[0].strip().lower()
    if mimetype_no_params == "*":
        mimetype_no_params = "*/*"

    type, subtype = typing.cast(
        typing.Tuple[str, str],
        mimetype_no_params.split("/", 1)
        if "/" in mimetype_no_params
        else (mimetype_no_params, ""),
    )
    subtype, suffix = typing.cast(
        typing.Tuple[str, str],
        subtype.split("+", 1) if "+" in subtype else (subtype, ""),
    )
    return MimeType(type=type, subtype=subtype, suffix=suffix, parameters=params)


@functools.lru_cache(128)
def is_known_encoding(encoding: str) -> typing.Optional[str]:
    """Given an encoding type, return either it's normalized name
    if we understand the codec otherwise return 'None'.
    """
    try:
        return codecs.lookup(encoding).name
    except LookupError:
        return None


def encoding_detector() -> chardet.UniversalDetector:
    """Gets an encoding detector object. Tries to use cChardet if available."""
    try:
        import cchardet

        return typing.cast(chardet.UniversalDetector, cchardet.UniversalDetector())
    except ImportError:
        return chardet.UniversalDetector()


def pretty_fingerprint(fingerprint: typing.Union[bytes, str]) -> str:
    if isinstance(fingerprint, str):
        fingerprint = binascii.unhexlify(fingerprint.replace(":", "").encode())
    return ":".join([INT_TO_HEX[x] for x in fingerprint])


def none_is_inf(value: typing.Optional[float]) -> float:
    return float("inf") if value is None else value


class BytesChunker:
    """Divides a stream of bytes into chunks"""

    def __init__(self, chunk_size: typing.Optional[int]):
        self.chunk_size = chunk_size
        self.byte_buffer = bytearray()

    def feed(self, data: bytes) -> typing.Iterable[bytes]:
        if self.chunk_size is None:
            return (data,)
        # TODO: Implement chunk_size

    def flush(self) -> typing.Iterable[bytes]:
        if self.chunk_size is None:
            return ()
        # TODO: Implement chunk_size


class TextChunker:
    """Decodes and divides a stream of bytes into chunks of text"""

    def __init__(self, encoding: str, chunk_size: typing.Optional[int]):
        self.encoding = encoding
        self.chunk_size = chunk_size

        self.string_buffer = ""
        self.byte_buffer = bytearray()

    def feed(self, data: bytes) -> typing.Iterable[str]:
        if self.chunk_size is None:
            return (data.decode(self.encoding),)
        # TODO: Implement chunk_size

    def flush(self) -> typing.Iterable[str]:
        if self.chunk_size is None:
            return ()
        # TODO: Implement chunk_size
