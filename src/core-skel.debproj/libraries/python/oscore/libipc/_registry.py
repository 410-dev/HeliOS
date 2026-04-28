"""
소켓 파일 네이밍 및 탐색.

파일명 형식: {process_name}_{pid}_{ipc_id}.sock
위치: LIBIPC_SOCK_DIR 환경변수 또는 /tmp/libipc/
"""
import os
import glob
import re
import hashlib

SOCK_DIR = os.environ.get("LIBIPC_SOCK_DIR", "/tmp/libipc")

def ensure_dir():
    os.makedirs(SOCK_DIR, mode=0o700, exist_ok=True)

def socket_path(process_name: str, executable: str, pid: int, ipc_id: str) -> str:
    ensure_dir()
    safe_name = _safe(process_name)
    safe_exec = _safe(executable)
    safe_id   = _safe(ipc_id)
    return os.path.join(SOCK_DIR, f"{safe_name}_{pid}_{safe_id}_{hashlib.md5(safe_exec.encode()).hexdigest()}.sock")

def find_sockets(process_name: str, pid: int, ipc_id: str, executable: str) -> list[str]:
    """
    프로세스명 + ipc_id 로 소켓 파일 목록을 탐색합니다.
    pid == -1 이면 모든 PID를 대상으로 합니다.
    """
    ensure_dir()
    safe_name = _safe(process_name)
    safe_id   = _safe(ipc_id)

    if pid == -1:
        pattern = os.path.join(SOCK_DIR, f"{safe_name}_*_{safe_id}")
    else:
        pattern = os.path.join(SOCK_DIR, f"{safe_name}_{pid}_{safe_id}")

    if executable is None:
        pattern += "_*.sock"
    else:
        safe_exec = _safe(executable)
        exec_hash = hashlib.md5(safe_exec.encode()).hexdigest()
        pattern += f"_{exec_hash}.sock"

    return glob.glob(pattern)

def _safe(s: str) -> str:
    """파일명에 안전하지 않은 문자를 제거합니다."""
    return re.sub(r"[^\w\-.]", "_", s)