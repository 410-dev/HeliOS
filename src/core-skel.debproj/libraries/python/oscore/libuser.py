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


def list_nosys_users() -> list[str]:
    nosys_users = []
    dat: list[dict[str, str | int]] = list_nosys_users_data()
    for d in dat:
        nosys_users.append(d['username'])
    return nosys_users

def list_nosys_users_data() -> list[dict[str, str | int]]:
    real_users = []

    # 시스템에 등록된 실제 사용 가능한 쉘 목록 (일반적으로 로그인 가능한 쉘들)
    # 직접 지정하거나 /etc/shells 파일을 읽어서 구성할 수 있습니다.
    valid_shells = ('/bin/bash', '/bin/sh', '/bin/zsh', '/usr/bin/bash', '/usr/bin/zsh')

    # 시스템의 모든 사용자 정보 가져오기
    for user in pwd.getpwall():
        # 1. UID가 1000 이상인 사용자 (단, 관례상 nobody 계정인 65534는 제외)
        # 2. 로그인 쉘이 nologin이나 false가 아닌 사용자
        if 1000 <= user.pw_uid < 65534:
            if user.pw_shell in valid_shells:
                real_users.append({
                    "username": user.pw_name,
                    "uid": user.pw_uid,
                    "gid": user.pw_gid,
                    "home": user.pw_dir,
                    "shell": user.pw_shell,
                    "comment": user.pw_gecos
                })

    return real_users


def get_user_uid(user: str = None) -> int:
    if user is None:
        return os.getuid()
    else:
        return pwd.getpwnam(user).pw_uid

