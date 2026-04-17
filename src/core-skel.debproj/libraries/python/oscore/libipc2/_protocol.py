"""
프레이밍 프로토콜:
  [4 bytes big-endian uint32: payload length][payload: JSON bytes]
"""
import json
import struct

HEADER = struct.Struct(">I")  # unsigned int, big-endian

def encode(obj: object) -> bytes:
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return HEADER.pack(len(payload)) + payload

def decode_from_socket(sock) -> object:
    """소켓에서 하나의 메시지를 읽어 파싱합니다."""
    header = _recv_exact(sock, HEADER.size)
    if not header:
        return None
    (length,) = HEADER.unpack(header)
    payload = _recv_exact(sock, length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))

def _recv_exact(sock, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)
