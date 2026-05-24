#!/usr/bin/env python3

# Usage
# runas <users> :: <command>

import sys
import shutil
import subprocess
import shlex
import oscore.libuser as libuser

def main():
    if len(sys.argv) < 4:
        print("Usage: runas <users> :: <command>")
        return 0

    if not libuser.is_current_user_root():
        print("Requires root privilege.")
        return 0

    # Get index of ::
    index: int = sys.argv.index("::")
    users_list: list[str] = sys.argv[1:index]
    command_list: list[str] = sys.argv[index+1:]

    # Execute command
    if not users_list:
        print("Error: at least one user is required before '::'", file=sys.stderr)
        print("Usage: runas <users> :: <command>", file=sys.stderr)
        return 2

    if not command_list:
        print("Error: command is required after '::'", file=sys.stderr)
        print("Usage: runas <users> :: <command>", file=sys.stderr)
        return 2

    # Optional dedupe while preserving order
    seen = set()
    ordered_users = []
    for user in users_list:
        if user not in seen:
            seen.add(user)
            ordered_users.append(user)

    # Prefer sudo; fall back to runuser if sudo is unavailable.
    sudo_path = shutil.which("sudo")
    runuser_path = shutil.which("runuser")

    last_nonzero = 0
    for user in ordered_users:

        # Substitute command with the username {user}
        new_cmd_list: list[str] = command_list.copy()
        new_cmd_list = [arg.replace("{user}", user) for arg in new_cmd_list]

        if sudo_path:
            cmd = [sudo_path, "-u", user, "--", *new_cmd_list]
        elif runuser_path:
            cmd = [runuser_path, "-u", user, "--", *new_cmd_list]
        else:
            print("Error: neither 'sudo' nor 'runuser' is available", file=sys.stderr)
            return 127

        print(f"[runas] {user}: {shlex.join(new_cmd_list)}", file=sys.stderr)
        result = subprocess.run(cmd)

        if result.returncode != 0:
            last_nonzero = result.returncode
            print(
                f"[runas] user '{user}' failed with exit code {result.returncode}",
                file=sys.stderr,
            )

    return last_nonzero

if __name__ == "__main__":
    sys.exit(main())
