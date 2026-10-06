import struct
from dataclasses import dataclass, field

MOVE_TO, LINE_TO, CLOSE_PATH = 1, 2, 7


@dataclass
class Feature:
    id: int | None
    type: int
    properties: dict
    geometry: list = field(default_factory=list)


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(data: bytes):
    pos = 0
    while pos < len(data):
        key, pos = _varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(data, pos)
            value, pos = data[pos : pos + size], pos + size
        elif wire == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"wire type {wire}")
        yield number, wire, value


def _packed(data: bytes) -> list[int]:
    values, pos = [], 0
    while pos < len(data):
        value, pos = _varint(data, pos)
        values.append(value)
    return values


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def _value(data: bytes):
    for number, _wire, raw in _fields(data):
        if number == 1:
            return raw.decode()
        if number == 2:
            return struct.unpack("<f", raw)[0]
        if number == 3:
            return struct.unpack("<d", raw)[0]
        if number == 4:
            return raw - (1 << 64) if raw >= 1 << 63 else raw
        if number == 5:
            return raw
        if number == 6:
            return _zigzag(raw)
        if number == 7:
            return bool(raw)
    return None


def _geometry(commands: list[int]) -> list[list[tuple[int, int]]]:
    parts, x, y, pos = [], 0, 0, 0
    while pos < len(commands):
        command, count = commands[pos] & 7, commands[pos] >> 3
        pos += 1
        if command == CLOSE_PATH:
            parts[-1].append(parts[-1][0])
            continue
        if command == MOVE_TO:
            parts.append([])
        for _ in range(count):
            x += _zigzag(commands[pos])
            y += _zigzag(commands[pos + 1])
            pos += 2
            parts[-1].append((x, y))
    return parts


def decode(tile: bytes) -> dict[str, list[Feature]]:
    layers = {}
    for number, _wire, layer_data in _fields(tile):
        if number != 3:
            continue
        name, keys, values, raw_features = None, [], [], []
        for lnum, _w, value in _fields(layer_data):
            if lnum == 1:
                name = value.decode()
            elif lnum == 2:
                raw_features.append(value)
            elif lnum == 3:
                keys.append(value.decode())
            elif lnum == 4:
                values.append(_value(value))
        features = []
        for raw in raw_features:
            fid, ftype, tags, commands = None, 0, [], []
            for fnum, _w, value in _fields(raw):
                if fnum == 1:
                    fid = value
                elif fnum == 2:
                    tags = _packed(value)
                elif fnum == 3:
                    ftype = value
                elif fnum == 4:
                    commands = _packed(value)
            properties = {
                keys[tags[i]]: values[tags[i + 1]] for i in range(0, len(tags), 2)
            }
            features.append(Feature(fid, ftype, properties, _geometry(commands)))
        layers[name] = features
    return layers
