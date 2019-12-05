import typing

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


class MimeType(typing.NamedTuple):
    type: str
    subtype: str
    suffix: str
    parameters: typing.Dict[str, typing.Optional[str]]


def parse_mimetype(mimetype: str) -> MimeType:
    """Mostly taken from aiohttp.utils"""
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

    fulltype = parts[0].strip().lower()
    if fulltype == "*":
        fulltype = "*/*"

    mtype, stype = (
        typing.cast(typing.Tuple[str, str], fulltype.split("/", 1))
        if "/" in fulltype
        else (fulltype, "")
    )
    stype, suffix = (
        typing.cast(typing.Tuple[str, str], stype.split("+", 1))
        if "+" in stype
        else (stype, "")
    )
    return MimeType(type=mtype, subtype=stype, suffix=suffix, parameters=params)
