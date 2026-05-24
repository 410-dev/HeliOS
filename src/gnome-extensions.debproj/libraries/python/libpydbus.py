import subprocess
import os
import oscore.libuser as user

def get_dbus_addr_path(username: str|None = None) -> str:
    uid = user.get_user_uid(username)
    return f"unix:path=/run/user/{uid}/bus"


def gsettings_set(path: str, key: str, value: str, as_user: str|None = None) -> bool:
    dbus_path = get_dbus_addr_path(as_user)
    cmd: list[str] = ["gsettings", "set", path, key, value]
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = dbus_path
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: Failed to set gsettings value. {result.stderr}")
        return False
    return True

def gsettings_get(path: str, key: str, as_user: str|None = None) -> str|None:
    dbus_path = get_dbus_addr_path(as_user)
    cmd: list[str] = ["gsettings", "get", path, key]
    env = os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"] = dbus_path
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: Failed to get gsettings value. {result.stderr}")
        return None
    return result.stdout.strip()
