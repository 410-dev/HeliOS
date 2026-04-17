#!/usr/bin/env python3

# Usage
# chprofile <username> <picture path> [--no-copy-to-home]

import sys
import os
import shutil
import subprocess
import pwd

# 프로필 사진 사본 만들기 (.face)
def copy_profile_picture_to_face(username: str, profile_pic_path: str) -> str:
    user_home_dir = f"/home/{username}/.local/share"
    target_profile_pic_path = os.path.join(user_home_dir, ".face")
    shutil.copyfile(profile_pic_path, target_profile_pic_path)
    shutil.chown(target_profile_pic_path, user=username, group=username)
    return target_profile_pic_path


# 프로필 사진 설정
def dbus_set_profile_picture(username: str, profile_pic_path: str):
    try:
        # dbus-send --system --dest=org.freedesktop.Accounts --print-reply /org/freedesktop/Accounts/User"$USER_ID" org.freedesktop.Accounts.User.SetIconFile string:"$IMAGE_PATH"
        user_info = pwd.getpwnam(username)
        user_id = user_info.pw_uid

        os.chmod(profile_pic_path, 0o644)
        wake_cmd = [
            "dbus-send",
            "--system",
            "--dest=org.freedesktop.Accounts",
            "--print-reply",
            "/org/freedesktop/Accounts",
            "org.freedesktop.Accounts.FindUserByName",
            f"string:{username}"
        ]
        result = subprocess.run(wake_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: Failed to wake up AccountsService.")
            return result.returncode, result.stdout, result.stderr

        result = subprocess.run([
            "dbus-send",
            "--system",
            "--dest=org.freedesktop.Accounts",
            "--print-reply",
            f"/org/freedesktop/Accounts/User{user_id}",
            "org.freedesktop.Accounts.User.SetIconFile",
            f"string:{profile_pic_path}"
        ], check=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error: Failed to set user home icon.")
            return result.returncode, result.stdout, result.stderr

        return 0, "", ""

    except Exception as e:
        print(f"Error: {e}")
        return 1, "", str(e)


def main():
    if len(sys.argv) < 3:
        print("Usage: chprofile <username> <picture path> [--no-copy-to-home]")
        return

    username = sys.argv[1]
    picture_path = sys.argv[2]
    no_copy_to_home = '--no-copy-to-home' in sys.argv

    updated_picture_path = picture_path
    if not no_copy_to_home:
        updated_picture_path = copy_profile_picture_to_face(username, picture_path)

    exit_code, _, _ = dbus_set_profile_picture(username, updated_picture_path)
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
