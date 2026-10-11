import struct
from collections.abc import Callable
from enum import IntEnum

from . import orjson


class Opcode(IntEnum):
    CONTINUE = 0x00
    TEXT = 0x01
    BINARY = 0x02
    CLOSE = 0x08
    PING = 0x09
    PONG = 0x0A


class CloseCode(IntEnum):
    CLEAN = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    INCORRECT_DATA = 1003
    ABNORMAL_CLOSURE = 1006
    INCONSISTENT_DATA = 1007
    MESSAGE_VIOLATING_POLICY = 1008
    MESSAGE_TOO_BIG = 1009
    EXTENSION_NEGOTIATION_FAILED = 1010
    SERVER_ERROR = 1011
    RESTART = 1012
    TRY_LATER = 1013
    BAD_GATEWAY = 1014
    SESSION_EXPIRED = 4001
    KEEP_ALIVE_TIMEOUT = 4002
    KILL_NOW = 4003


class ConnectionState(IntEnum):
    OPEN = 0
    CLOSING = 1
    CLOSED = 2


DATA_OP = {Opcode.TEXT, Opcode.BINARY}
CTRL_OP = {Opcode.CLOSE, Opcode.PING, Opcode.PONG}
HEARTBEAT_OP = {Opcode.PING, Opcode.PONG}

VALID_CLOSE_CODES = {
    code for code in CloseCode if code is not CloseCode.ABNORMAL_CLOSURE
}
APPLICATION_CLOSE_CODES = range(3000, 5000)

MAX_CONTROL_PAYLOAD = 125

_XOR_TABLE = [bytes(a ^ b for a in range(256)) for b in range(256)]


class WebsocketError(Exception):
    pass


class InvalidCloseCodeError(WebsocketError):
    def __init__(self, code) -> None:
        super().__init__(f"Invalid close code: {code}")


class PayloadTooLargeError(WebsocketError):
    pass


class ProtocolError(WebsocketError):
    pass


class Frame:
    __slots__ = ("fin", "opcode", "payload", "rsv1", "rsv2", "rsv3")

    def __init__(
        self, opcode, payload=b"", fin=True, rsv1=False, rsv2=False, rsv3=False
    ) -> None:
        self.opcode = opcode
        self.payload = payload
        self.fin = fin
        self.rsv1 = rsv1
        self.rsv2 = rsv2
        self.rsv3 = rsv3


class CloseFrame(Frame):
    __slots__ = ("code", "reason")

    MAX_REASON_LENGTH = MAX_CONTROL_PAYLOAD - 2

    def __init__(self, code, reason) -> None:
        if code not in VALID_CLOSE_CODES and code not in APPLICATION_CLOSE_CODES:
            raise InvalidCloseCodeError(code)
        payload = struct.pack("!H", code)
        if reason:
            encoded_reason = reason.encode("utf-8")
            if len(encoded_reason) > self.MAX_REASON_LENGTH:
                reason = encoded_reason[: self.MAX_REASON_LENGTH].decode(
                    "utf-8", errors="ignore"
                )
                encoded_reason = reason.encode("utf-8")
            payload += encoded_reason
        self.code = code
        self.reason = reason
        super().__init__(Opcode.CLOSE, payload)


def parse_close_payload(payload) -> tuple[int, str | None]:
    if len(payload) >= 2:
        code = struct.unpack("!H", payload[:2])[0]
        if code not in VALID_CLOSE_CODES and code not in APPLICATION_CLOSE_CODES:
            return CloseCode.PROTOCOL_ERROR, "Invalid close code"
        try:
            return code, bytes(payload[2:]).decode("utf-8")
        except UnicodeDecodeError:
            return CloseCode.INCONSISTENT_DATA, "Malformed close reason"
    if payload:
        return CloseCode.PROTOCOL_ERROR, "Malformed closing frame"
    return CloseCode.CLEAN, None


def unmask(payload: bytearray, mask) -> bytearray:
    a, b, c, d = (_XOR_TABLE[n] for n in mask)
    payload[::4] = payload[::4].translate(a)
    payload[1::4] = payload[1::4].translate(b)
    payload[2::4] = payload[2::4].translate(c)
    payload[3::4] = payload[3::4].translate(d)
    return payload


def encode_frame(frame: Frame) -> bytes:
    if isinstance(frame.payload, str):
        frame.payload = frame.payload.encode("utf-8")
    elif not isinstance(frame.payload, (bytes, bytearray)):
        frame.payload = orjson.dumps(frame.payload)
    if frame.opcode in CTRL_OP and len(frame.payload) > MAX_CONTROL_PAYLOAD:
        raise ProtocolError(
            "Control frames should have a payload length smaller than 126"
        )
    first_byte = (
        (0b10000000 if frame.fin else 0)
        | (0b01000000 if frame.rsv1 else 0)
        | (0b00100000 if frame.rsv2 else 0)
        | (0b00010000 if frame.rsv3 else 0)
        | frame.opcode
    )
    length = len(frame.payload)
    if length < 126:
        head = struct.pack("!BB", first_byte, length)
    elif length < 65536:
        head = struct.pack("!BBH", first_byte, 126, length)
    else:
        head = struct.pack("!BBQ", first_byte, 127, length)
    return head + frame.payload


class FrameParser:
    __slots__ = ("_announced", "_buffer", "max_size", "on_header")

    def __init__(
        self, max_size: int, on_header: Callable[[Opcode], None] | None = None
    ) -> None:
        self.max_size = max_size
        self.on_header = on_header
        self._buffer = bytearray()
        self._announced = False

    @property
    def mid_frame(self) -> bool:
        return bool(self._buffer)

    def feed(self, data) -> list[Frame]:
        if data:
            self._buffer += data
        frames = []
        while (frame := self._next_frame()) is not None:
            frames.append(frame)
        return frames

    def _next_frame(self) -> Frame | None:
        buffer = self._buffer
        if len(buffer) < 2:
            return None
        first_byte, second_byte = buffer[0], buffer[1]
        try:
            opcode = Opcode(first_byte & 0b00001111)
        except ValueError as exc:
            raise ProtocolError(exc) from exc
        if not self._announced:
            self._announced = True
            if self.on_header is not None:
                self.on_header(opcode)
        fin = bool(first_byte & 0b10000000)
        rsv1 = bool(first_byte & 0b01000000)
        rsv2 = bool(first_byte & 0b00100000)
        rsv3 = bool(first_byte & 0b00010000)
        if rsv1 or rsv2 or rsv3:
            raise ProtocolError("Reserved bits must be unset")
        if not second_byte & 0b10000000:
            raise ProtocolError("Frame must be masked")
        length = second_byte & 0b01111111
        if opcode in CTRL_OP:
            if not fin:
                raise ProtocolError("Control frames cannot be fragmented")
            if length > MAX_CONTROL_PAYLOAD:
                raise ProtocolError("Control frames payload must be smaller than 126")
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                return None
            length = struct.unpack_from("!H", buffer, 2)[0]
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                return None
            length = struct.unpack_from("!Q", buffer, 2)[0]
            if length >> 63:
                raise ProtocolError("The most significant bit of a length must be 0")
            offset = 10
        if length > self.max_size:
            raise PayloadTooLargeError
        end = offset + 4 + length
        if len(buffer) < end:
            return None
        mask = bytes(buffer[offset : offset + 4])
        payload = unmask(buffer[offset + 4 : end], mask)
        del buffer[:end]
        self._announced = False
        return Frame(opcode, bytes(payload), fin, rsv1, rsv2, rsv3)
