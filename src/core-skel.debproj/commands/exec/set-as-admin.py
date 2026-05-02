#!/usr/bin/env python3

import sys
import subprocess
import oscore.libuser as libuser


# Usage:
#   set-as-admin +user1 -user2 # Add user1 as admin, remove user2 from admin

def main(args: list[str]) -> int:
    # Check if privileged
    if not libuser.is_current_user_privileged_as_admin():
        print(f"This script must be run as root or should be privileged as administrator group ({libuser.GROUP_Administrator()}).")
        return 1

    # Get usernames in args
    usernames = [arg for arg in args if arg.startswith("+") or arg.startswith("-")]

    for username in usernames:
        user_in_group: bool = libuser.is_user_in_group(username, libuser.GROUP_Administrator())
        add_mode: bool = username.startswith("+")
        username = username[1:]  # Remove + or -

        if add_mode and not user_in_group:
            # Add user to admin group
            subprocess.run(["usermod", "-aG", libuser.GROUP_Administrator(), username], check=True)
            print(f"[+] Added {username} to {libuser.GROUP_Administrator()}")
        elif not add_mode and user_in_group:
            # Remove user from admin group
            subprocess.run(["gpasswd", "-d", username, libuser.GROUP_Administrator()], check=True)
            print(f"[-] Removed {username} from {libuser.GROUP_Administrator()}")
        else:
            print(f"[=] No change for {username} (add_mode={add_mode}, user_in_group={user_in_group})")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))