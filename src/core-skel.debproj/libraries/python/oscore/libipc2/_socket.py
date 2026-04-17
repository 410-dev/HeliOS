import os
import socket
import threading
import logging
from typing import Callable

from . import _protocol as proto
from . import _registry as reg

log = logging.getLogger("libipc")

class ListenerServer:
    """단일 IPC 엔드포인트를 수신 대기하는 UNIX 소켓 서버."""

    def __init__(
        self,
        process_name: str,
        executable: str,
        pid: int,
        ipc_id: str,
        callback: Callable,
        return_type: type | None,
    ):
        self.path        = reg.socket_path(process_name, executable, pid, ipc_id)
        self.callback    = callback
        self.return_type = return_type
        self._sock       = None
        self._thread     = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    def start(self):
        # 이전 소켓 파일 정리
        if os.path.exists(self.path):
            os.unlink(self.path)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.path)
        self._sock.listen(64)
        self._sock.settimeout(1.0)   # accept() 블로킹 타임아웃

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        log.info(f"[libipc] listening on {self.path}")

    def stop(self):
        self._stop_event.set()
        if self._sock:
            self._sock.close()
        if os.path.exists(self.path):
            os.unlink(self.path)
        log.info(f"[libipc] stopped {self.path}")

    # ------------------------------------------------------------------
    def _serve(self):
        while not self._stop_event.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            t.start()

    def _handle(self, conn: socket.socket):
        try:
            msg = proto.decode_from_socket(conn)
            if msg is None:
                return

            from_info: dict | None = msg.get("from")   # anonymous 시 None
            data                   = msg.get("data")

            try:
                result = self.callback(from_info, data)
            except Exception as exc:
                reply = {"ok": False, "error": str(exc), "data": None}
            else:
                reply = {"ok": True, "error": None, "data": result}

            conn.sendall(proto.encode(reply))
        except Exception as exc:
            log.warning(f"[libipc] handler error: {exc}")
        finally:
            conn.close()


# -----------------------------------------------------------------------
def send_message(
    process_name: str,
    pid: int,
    ipc_id: str,
    data,
    return_type: type | None,
    sender_info: dict | None,   # None → anonymous
    executable: str = None,
    timeout: float = 5.0,
):
    paths = reg.find_sockets(process_name, pid, ipc_id, executable)
    if not paths:
        raise ConnectionError(
            f"[libipc] no socket found for '{process_name}' / pid={pid} / id='{ipc_id}'"
        )

    # pid == -1 이고 여러 개면 첫 번째 매칭 사용 (정책 변경 가능)
    path = paths[0]

    msg = {
        "from": sender_info,
        "data": data,
    }

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(proto.encode(msg))

        reply = proto.decode_from_socket(s)

    if reply is None:
        raise RuntimeError("[libipc] empty reply from listener")

    if not reply.get("ok"):
        raise RuntimeError(f"[libipc] remote error: {reply.get('error')}")

    return reply.get("data")
