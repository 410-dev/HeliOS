import os
import tempfile
import sys


# ==========================================
# 1. 파일 잠금(File Locking) OS별 분기 처리
# ==========================================
if sys.platform == "win32":
    import msvcrt


    def _lock_file(f):
        # 현재 포인터 위치를 저장하고 0으로 이동하여 1바이트 크기만큼 잠금 설정
        pos = f.tell()
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        f.seek(pos)


    def _unlock_file(f):
        pos = f.tell()
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.seek(pos)
else:
    import fcntl


    def _lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

# ==========================================
# 2. Atomic Write 구현 (임시 파일 후 Replace)
# ==========================================
def _atomic_write_core(path: str, content, is_binary: bool, encoding: str = None):
    dir_name = os.path.dirname(path) or "."
    base_name = os.path.basename(path)

    # 임시 파일 생성 (동일한 디렉토리 내에 생성해야 원자적 replace 보장)
    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=base_name + ".tmp~")
    mode = "wb" if is_binary else "w"

    try:
        # mkstemp가 반환한 파일 디스크립터(fd)를 직접 사용하여 충돌 방지
        with open(fd, mode, encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # OS 버퍼의 내용을 디스크에 강제 기록

        # 안전하게 모두 기록된 후 기존 파일과 교체
        os.replace(temp_path, path)
    except Exception:
        # 실패 시 임시 파일 찌꺼기 정리
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def atomic_write(path: str, content: str, encoding: str = "utf-8"):
    _atomic_write_core(path, content, is_binary=False, encoding=encoding)


def atomic_write_bin(path: str, content: bytes):
    _atomic_write_core(path, content, is_binary=True)


# ==========================================
# 3. Locking Write 구현 (Lock 획득 후 Truncate)
# ==========================================
def _locking_write_core(path: str, content, is_binary: bool, encoding: str = None):
    # 'w' 모드로 열면 락을 걸기도 전에 내용이 날아가므로 'a'(append) 모드로 엽니다.
    mode = "ab" if is_binary else "a"

    with open(path, mode, encoding=encoding) as f:
        _lock_file(f)
        # fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()  # 락을 획득한 후 안전한 상태에서 기존 내용을 비움
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        finally:
            _unlock_file(f)
            # fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def locking_write(path: str, content: str, encoding: str = "utf-8"):
    _locking_write_core(path, content, is_binary=False, encoding=encoding)


def locking_write_bin(path: str, content: bytes):
    _locking_write_core(path, content, is_binary=True)