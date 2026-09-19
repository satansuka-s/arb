from pathlib import Path

from sources.sporthub.parser import SporthubParser, read_fields


def test_varint_and_protobuf_reader():
    # field 1 = 150
    payload = bytes([0x08, 0x96, 0x01])
    assert read_fields(payload)[1] == [150]


def test_length_delimited_reader():
    payload = bytes([0x0A, 0x03]) + b"abc"
    assert read_fields(payload)[1] == [b"abc"]


def test_sporthub_parser_does_not_drop_unknown_league(tmp_path: Path):
    parser = SporthubParser(tmp_path / "league.json", tmp_path / "sports.json")
    # Build a minimal event wrapper using the same protobuf field numbers as the source.
    def vi(value: int) -> bytes:
        out = bytearray()
        while value >= 128:
            out.append((value & 127) | 128)
            value >>= 7
        out.append(value)
        return bytes(out)

    def fld(num: int, data: bytes) -> bytes:
        return vi(num << 3 | 2) + vi(len(data)) + data

    def var(num: int, value: int) -> bytes:
        return vi(num << 3) + vi(value)

    team1 = fld(1, var(1, 10) + fld(2, b"a") + fld(3, b"Alpha"))
    team2 = fld(3, var(1, 20) + fld(2, b"b") + fld(3, b"Beta"))
    teams = team1 + team2
    league = (
        var(1, 12345)
        + fld(5, b"ext")
        + var(10, 999999)
        + fld(16, teams)
        + fld(13, b"2026-09-17T12:00:00Z")
    )
    event = fld(1, league)
    wrapper = fld(6, event)
    frame = fld(29, wrapper)

    result = parser.parse_frame(frame)
    assert len(result) == 1
    assert result[0].event_id == "12345"
    assert result[0].sport == "unknown"
