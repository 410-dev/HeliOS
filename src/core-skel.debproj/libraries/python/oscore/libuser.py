import grp
import os
import pwd


def GROUP_Administrator() -> str:
    return 'Administrator'

def current_username() -> str:
    return pwd.getpwuid(os.getuid()).pw_name

def is_user_in_group(username, group_name) -> bool:
    try:
        # Get the list of users explicitly listed in the group
        group_info = grp.getgrnam(group_name)
        if username in group_info.gr_mem:
            return True

        # Also check if the group is the user's primary group
        user_info = pwd.getpwnam(username)
        primary_group_info = grp.getgrgid(user_info.pw_gid)
        if primary_group_info.gr_name == group_name:
            return True

        return False
    except KeyError:
        # Group or User does not exist
        return False


def is_current_user_in_group(group_name) -> bool:
    return is_user_in_group(current_username(), group_name)


def is_current_user_privileged(group_name) -> bool:
    return os.getuid() == 0 or is_current_user_in_group(group_name)


def is_current_user_privileged_as_admin() -> bool:
    return is_current_user_privileged(GROUP_Administrator())


def is_current_user_root() -> bool:
    return os.getuid() == 0