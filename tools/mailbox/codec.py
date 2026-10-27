"""Draft-1 wire format. No sockets, clocks or hardware access."""

from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib

FIFO_DEPTH = 16
MAX_DATA = 2048
MAX_PAYLOAD = 2080
MAX_FRAME = 2100
MAX_UDP = 1472
HEADER = struct.Struct("<2sBBIIBBH")
HELLO_LIMITS = struct.pack("<HHBBBBH6x", MAX_PAYLOAD, MAX_DATA, 16, 16, 4, 3, 1500)


class FormatError(ValueError):
    """Invalid wire representation, distinct from a public UNAPI error."""


class Kind(IntEnum):
    HELLO = 0
    REQUEST = 1
    RESPONSE = 2
    ACK = 3


@dataclass(frozen=True)
class Header:
    kind: Kind
    session: int
    sequence: int
    opcode: int
    status: int = 0
    length: int = 0

    def encode(self) -> bytes:
        if not (1 <= self.session <= 0xFFFFFFFF and
                0 <= self.sequence < 0xFFFFFFFF and
                0 <= self.opcode <= 255 and 0 <= self.length <= MAX_PAYLOAD):
            raise FormatError("header field outside draft limits")
        if not isinstance(self.kind, Kind) or self.status not in (0, 1):
            raise FormatError("unknown kind or status")
        if self.kind != Kind.RESPONSE and self.status:
            raise FormatError("only a response can carry transport status")
        if self.status and self.length:
            raise FormatError("transport error response must have no payload")
        return HEADER.pack(b"N4", 1, self.kind, self.session, self.sequence,
                           self.opcode, self.status, self.length)

    @classmethod
    def decode(cls, data: bytes) -> "Header":
        if len(data) != HEADER.size:
            raise FormatError("header must be 16 bytes")
        magic, version, kind, session, seq, op, status, length = HEADER.unpack(data)
        if magic != b"N4" or version != 1:
            raise FormatError("magic/version mismatch")
        try:
            result = cls(Kind(kind), session, seq, op, status, length)
            result.encode()
        except ValueError as exc:
            raise FormatError(str(exc)) from exc
        return result


@dataclass(frozen=True)
class Frame:
    header: Header
    payload: bytes = b""

    def encode(self) -> bytes:
        if len(self.payload) != self.header.length:
            raise FormatError("payload length does not match header")
        wire = self.header.encode() + self.payload
        return wire + struct.pack("<I", zlib.crc32(wire))

    @classmethod
    def make(cls, kind: Kind, session: int, sequence: int, opcode: int,
             payload: bytes = b"", status: int = 0) -> "Frame":
        return cls(Header(kind, session, sequence, opcode, status, len(payload)), payload)

    @classmethod
    def decode(cls, wire: bytes) -> "Frame":
        header = Header.decode(wire[:16])
        if len(wire) != 20 + header.length:
            raise FormatError("incomplete or trailing frame bytes")
        if zlib.crc32(wire[:-4]) != struct.unpack("<I", wire[-4:])[0]:
            raise FormatError("CRC mismatch")
        return cls(header, wire[16:-4])


@dataclass(frozen=True)
class Call:
    a: int
    f: int = 0
    b: int = 0
    c: int = 0
    d: int = 0
    e: int = 0
    h: int = 0
    l: int = 0
    ix: int = 0
    iy: int = 0
    aux: bytes = b""
    data: bytes = b""

    @property
    def bc(self) -> int:
        return self.b * 256 + self.c

    @property
    def de(self) -> int:
        return self.d * 256 + self.e

    @property
    def hl(self) -> int:
        return self.h * 256 + self.l

    @classmethod
    def make(cls, a: int, *, bc=None, de=None, hl=None, **fields) -> "Call":
        for pair, value in (("bc", bc), ("de", de), ("hl", hl)):
            if value is not None:
                if not 0 <= value <= 65535:
                    raise FormatError("register pair outside 16-bit range")
                if any(register in fields for register in pair):
                    raise FormatError("register pair specified twice")
                fields[pair[0]], fields[pair[1]] = value >> 8, value & 255
        return cls(a=a, **fields)

    def encode(self) -> bytes:
        if (len(self.aux) > 16 or len(self.data) > MAX_DATA or self.f or self.iy):
            raise FormatError("call exceeds limits or sets reserved registers")
        try:
            registers = bytes((self.a, self.f, self.b, self.c,
                               self.d, self.e, self.h, self.l))
            tail = struct.pack("<HHBBH", self.ix, self.iy, len(self.aux), 0, len(self.data))
        except (ValueError, struct.error) as exc:
            raise FormatError("register outside wire range") from exc
        return registers + tail + self.aux.ljust(16, b"\0") + self.data

    @classmethod
    def decode(cls, payload: bytes) -> "Call":
        if not 32 <= len(payload) <= MAX_PAYLOAD:
            raise FormatError("call record size")
        ix, iy, aux_len, reserved, data_len = struct.unpack("<HHBBH", payload[8:16])
        if (aux_len > 16 or reserved or data_len > MAX_DATA or
                len(payload) != 32 + data_len or any(payload[16 + aux_len:32])):
            raise FormatError("call length/reserved bytes")
        result = cls(*payload[:8], ix, iy, payload[16:16 + aux_len], payload[32:])
        result.encode()
        return result


def validate_request(opcode: int, call: Call) -> None:
    """Validate marshaling before committing a command, not public parameters."""
    if call.a != opcode:
        raise FormatError("opcode and input A disagree")
    # Only the modeled subset has a complete marshaling schema here.
    schemas = {
        8: ("bhl", 0, False), 9: ("b", 0, False), 10: ("b", 0, False),
        11: ("b", 8, True), 12: ("bde", 0, False), 13: ("", 11, False),
        14: ("b", 0, False), 15: ("b", 0, False), 16: ("b", 0, False),
        17: ("bchl", 0, True), 18: ("bhl", 0, False),
    }
    if opcode not in schemas:
        return
    registers, aux_len, has_data = schemas[opcode]
    if len(call.aux) != aux_len or (call.data and not has_data) or call.ix:
        raise FormatError("unexpected parameter block/data/register")
    if any(getattr(call, name) for name in "bcdehl" if name not in registers):
        raise FormatError("unused register or MSX pointer is nonzero")
    if opcode == 17 and call.hl != len(call.data):
        raise FormatError("TCP send length disagrees with inline bytes")
    if opcode == 11 and int.from_bytes(call.aux[6:8], "little") != len(call.data):
        raise FormatError("UDP send length disagrees with inline bytes")


def validate_response(request: Call, reply: Call) -> None:
    """Check copy-relevant metadata for the modeled subset before host ACK."""
    if request.a not in range(8, 19):
        return
    if not 0 <= reply.a <= 15:
        raise FormatError("unknown public error code")
    if reply.a:
        if reply.aux or reply.data:
            raise FormatError("failed call carries caller-buffer data")
        return
    if len(reply.aux) != (8 if request.a == 16 else 0):
        raise FormatError("unexpected result parameter block")
    if request.a == 12:
        if reply.bc > MAX_UDP or len(reply.data) != min(request.de, reply.bc):
            raise FormatError("UDP result length disagrees with copy limit")
    elif request.a == 18:
        if reply.bc != len(reply.data) or reply.bc > request.hl or reply.hl:
            raise FormatError("TCP result length/urgent count mismatch")
    elif reply.data:
        raise FormatError("unexpected inline result data")
    if request.a in (8, 13) and not 1 <= reply.b <= 3:
        raise FormatError("application handle outside negotiated pool")
