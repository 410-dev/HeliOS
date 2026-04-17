"""
libipc — UNIX 소켓 기반 경량 IPC 라이브러리
"""
import os
import sys
import atexit
import logging
from typing import Callable

from ._socket      import ListenerServer, send_message
from ._sender_info import build_sender_info

__all__ = ["add_listener", "remove_listener", "send", "send_anonymous"]

log = logging.getLogger("libipc")

# 등록된 리스너 테이블  { ipc_id → ListenerServer }
_listeners: dict[str, ListenerServer] = {}

# def _current_process_name() -> str:
#     return os.path.basename(sys.argv[0])

# -----------------------------------------------------------------------
# 공개 API
# -----------------------------------------------------------------------

def add_listener(
    process_name: str,
    ipc_id: str,
    callback: Callable,
    return_type: type | None = None,
) -> ListenerServer:
    """
    IPC 엔드포인트를 등록하고 수신을 시작합니다.

    소켓 파일명: {process_name}_{pid}_{ipc_id}.sock
    """
    if ipc_id in _listeners:
        raise ValueError(f"[libipc] listener '{ipc_id}' is already registered")

    server = ListenerServer(
        process_name = process_name,
        executable   = sys.argv[0],
        pid          = os.getpid(),
        ipc_id       = ipc_id,
        callback     = callback,
        return_type  = return_type,
    )
    server.start()
    _listeners[ipc_id] = server
    return server


def remove_listener(ipc_id: str):
    """등록된 리스너를 중지하고 소켓 파일을 제거합니다."""
    server = _listeners.pop(ipc_id, None)
    if server:
        server.stop()
    else:
        log.warning(f"[libipc] listener '{ipc_id}' not found")


def send(
    process_name: str,
    pid: int,
    ipc_id: str,
    data,
    return_type: type | None = None,
    executable: str = None,
    timeout: float = 5.0,
):
    """
    대상 프로세스의 IPC 엔드포인트로 메시지를 보내고 응답을 반환합니다.
    발신자 정보(from)가 포함됩니다.
    """
    sender_info = build_sender_info(return_type)
    return send_message(process_name, pid, ipc_id, data, return_type, sender_info, executable, timeout)


def send_anonymous(
    process_name: str,
    pid: int,
    ipc_id: str,
    data,
    return_type: type | None = None,
    executable: str = None,
    timeout: float = 5.0,
):
    """
    send() 와 동일하지만 from 데이터를 포함하지 않습니다.
    """
    return send_message(process_name, pid, ipc_id, data, return_type, None, executable, timeout)


# -----------------------------------------------------------------------
# 프로세스 종료 시 모든 리스너 정리
# -----------------------------------------------------------------------
@atexit.register
def _cleanup():
    for ipc_id in list(_listeners.keys()):
        remove_listener(ipc_id)
