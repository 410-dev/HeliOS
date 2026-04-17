import os
import pwd
import grp
import sys

def build_sender_info(expecting_return_type: type | None) -> dict:
    """현재 프로세스의 발신자 정보를 빌드합니다."""
    uid  = os.getuid()
    euid = os.geteuid()
    gid  = os.getgid()

    try:
        pw      = pwd.getpwuid(uid)
        username = pw.pw_name
        home_dir = pw.pw_dir
    except KeyError:
        username = str(uid)
        home_dir = ""

    try:
        group = grp.getgrgid(gid).gr_name
    except KeyError:
        group = str(gid)

    return {
        "process_name": sys.argv[0],
        "process_simple_name": os.path.basename(sys.argv[0]),
        "pid":          os.getpid(),
        "uid":          uid,
        "euid":         euid,
        "gid":          gid,
        "username":     username,
        "group":        group,
        "home_dir":     home_dir,
        "cmdline":      sys.argv[:],
        "expecting_return_type": expecting_return_type.__name__ if expecting_return_type else None,
    }