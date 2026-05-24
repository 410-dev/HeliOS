#!/usr/bin/env python3

# Usage
# enum-users

import sys
import oscore.libuser as libuser

def main():

    multi_liner: bool = False
    if '-1' in sys.argv:
        multi_liner = True

    non_sys_users: list[str] = libuser.list_nosys_users()

    if multi_liner:
        for user in non_sys_users:
            print(user)
    else:
        print(" ".join(non_sys_users))

    return 0


if __name__ == "__main__":
    sys.exit(main())
