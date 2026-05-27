import os
import glob
import shutil
import subprocess
from typing import Optional


# DE 핵심 프로세스 매핑
DE_PROCESS_MAP = [
    (["gnome-shell", "gnome-session-b"], "GNOME"),
    (["plasmashell", "kwin_x11", "kwin_wayland"], "KDE"),
    (["xfce4-session"],                            "XFCE"),
    (["mate-session"],                             "MATE"),
    (["cinnamon"],                                 "Cinnamon"),
    (["lxsession"],                                "LXDE"),
    (["lxqt-session"],                             "LXQt"),
    (["budgie-panel", "budgie-wm"],                "Budgie"),
    (["i3"],                                       "i3"),
    (["sway"],                                     "Sway"),
    (["openbox"],                                  "Openbox"),
    (["bspwm"],                                    "bspwm"),
    (["hyprland"],                                 "Hyprland"),
]


def _from_env() -> Optional[str]:
    """1순위: 환경변수 직접 확인."""
    return os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")


def _from_loginctl() -> Optional[str]:
    """2순위: loginctl로 systemd 세션 조회 (SSH/서비스 환경에서 신뢰도 높음)."""
    if not shutil.which("loginctl"):
        return None
    try:
        timeout: int = 1
        sessions = subprocess.check_output(
            ["loginctl", "list-sessions", "--no-legend"],
            text=True, timeout=timeout
        ).splitlines()

        for line in sessions:
            parts = line.split()
            if not parts:
                continue
            sid = parts[0]

            # 그래픽 세션(x11/wayland)만 대상
            session_type = subprocess.check_output(
                ["loginctl", "show-session", sid, "-p", "Type"],
                text=True, timeout=timeout
            ).strip()
            if not any(t in session_type for t in ("x11", "wayland", "mir")):
                continue

            desktop = subprocess.check_output(
                ["loginctl", "show-session", sid, "-p", "Desktop"],
                text=True, timeout=timeout
            ).strip()
            # "Desktop=GNOME" 형식
            value = desktop.split("=", 1)[-1]
            if value and value != "Desktop":
                return value

    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None


def _from_proc_environ() -> Optional[str]:
    """3순위: /proc/*/environ 스캔으로 실행 중인 세션의 환경변수 탈취."""
    for path in glob.iglob("/proc/*/environ"):
        try:
            with open(path, "rb") as f:
                data = f.read()
            # null-byte로 분리된 환경변수 파싱
            for entry in data.split(b"\x00"):
                if entry.startswith(b"XDG_CURRENT_DESKTOP="):
                    value = entry.split(b"=", 1)[1].decode(errors="replace").strip()
                    if value:
                        return value
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
    return None


def _from_ps() -> Optional[str]:
    """4순위: ps 프로세스 이름 매칭 (폴백)."""
    try:
        procs = subprocess.check_output(
            ["ps", "-eo", "comm="],
            text=True, timeout=5
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    running = set(procs.splitlines())

    for process_names, de_name in DE_PROCESS_MAP:
        if any(p in running for p in process_names):
            return de_name
    return None


def detect_desktop_environment() -> str:
    """
    환경변수 없이도 동작하는 DE 탐지.
    SSH, systemd 서비스 환경에서도 사용 가능.

    탐지 순서:
      1. 환경변수 (XDG_CURRENT_DESKTOP / DESKTOP_SESSION)
      2. loginctl (systemd 세션 메타데이터)
      3. /proc/*/environ 스캔 (실행 중 프로세스의 환경변수)
      4. ps 프로세스 이름 매칭

    Returns:
        탐지된 DE 이름, 실패 시 "Unknown"
    """
    strategies = [
        ("env",      _from_env),
        ("loginctl", _from_loginctl),
        ("proc",     _from_proc_environ),
        ("ps",       _from_ps),
    ]

    for name, fn in strategies:
        result = fn()
        if result:
            return result

    return "Unknown"
