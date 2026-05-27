import subprocess
import os
import oscore.libuser as user
import oscore.desktop.environment as desktop_detection

## =============
##  Helpers
## =============

def username_auto(username: str|None) -> str:
    return user.current_username() if username is None or not username else username

def uid_auto(username: str|None) -> int:
    return user.get_user_uid(username_auto(username))

def dbus_addr(username: str | None = None) -> str:
    return f"unix:path=/run/user/{uid_auto(username)}/bus"

def dbus_avail(username: str | None = None) -> bool:
    return os.path.exists(dbus_addr(username)[len("unix:path="):])

def wayland_socket(of_user: str | None = None, idx: int = 0) -> str | None:
    path = f"/run/user/{uid_auto(of_user)}/wayland-{idx}"
    return path if os.path.exists(path) else None

def wayland_socket_avail(of_user: str | None = None, idx: int = 0) -> bool:
    return wayland_socket(of_user, idx) is not None

def desktop_environment_session() -> str:
    return desktop_detection.detect_desktop_environment()

def x11_avail(idx: int = 0) -> bool:
    socket_candidates: list[str] = [
        f"/tmp/.X{idx}-lock",
        f"/tmp/.X11-unix/X{idx}"
    ]
    for socket in socket_candidates:
        if os.path.exists(socket):
            return True
    return False

## =============
## Objects
## =============

class DBUSExecutionEnvironment:
    def __init__(self, dbus: bool, graphic: bool, as_user: str | None = None, env: dict | None = None) -> None:
        self.username = username_auto(as_user)
        self.uid = uid_auto(self.username)
        self.env = {}
        self.session = desktop_environment_session()
        self.init_env(dbus, graphic, env)

    def init_env(self, dbus: bool, graphical: bool, default_env: dict | None = None) -> None:
        self.env = os.environ.copy()
        if default_env:
            self.env.update(default_env)

        if graphical:
            dbus = True
            stat: SessionAvailabilityReport = SessionAvailabilityReport(self.username)

            # XWayland
            if stat.X11 or stat.WAYLAND: self.assign_ifnot("DISPLAY", ":0")
            # Wayland
            if stat.WAYLAND:
                self.assign_ifnot("WAYLAND_DISPLAY", "wayland-0")
                self.assign_ifnot("XDG_SESSION_TYPE", "wayland")
            # X11
            elif stat.X11: self.assign_ifnot("XDG_SESSION_TYPE", "x11")
            self.assign_ifnot("XDG_CURRENT_DESKTOP", self.session)

        if dbus and dbus_avail(self.username):
            self.assign_ifnot("DBUS_SESSION_BUS_ADDRESS", dbus_addr(self.username))
            self.assign_ifnot("XDG_RUNTIME_DIR", f"/run/user/{self.uid}")

    def assign_write(self, key: str, value: str) -> None:
        self.env[key] = value

    def assign_ifnot(self, key: str, value: str) -> None:
        if key not in self.env or not self.env[key]:
            self.env[key] = value

    def compose(self) -> dict:
        return self.env

    def gsettings_set(self, path: str, key: str, value: str) -> bool:
        cmd: list[str] = ["gsettings", "set", path, key, value]
        success, stdout, stderr = self.exec(cmd)
        if not success:
            print(f"Error: Failed to set gsettings value. {stderr}")
        return success

    def gsettings_get(self, path: str, key: str) -> str | None:
        cmd: list[str] = ["gsettings", "get", path, key]
        success, stdout, stderr = self.exec(cmd)
        if not success:
            print(f"Error: Failed to get gsettings value. {stderr}")
            return None
        return stdout.strip()

    def exec(self, cmd: list[str]) -> tuple[bool, str, str]:
        result = subprocess.Popen(cmd, env=self.compose(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = result.communicate()
        success = (result.returncode == 0)
        if not success:
            print(f"Error: Failed to execute command. {stderr}")
        return success, stdout.strip(), stderr.strip()


class SessionAvailabilityReport:
    def __init__(self, username: str | None = None, display_index: int = 0) -> None:
        self.DBUS = dbus_avail(username)
        self.WAYLAND = wayland_socket_avail(username, display_index)
        self.X11 = x11_avail(display_index)
        self.XWAYLAND = self.WAYLAND and self.X11
