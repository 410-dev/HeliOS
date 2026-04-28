#!/usr/bin/env python3

# Usage
# postlogonconfig
# postlogonconfig --user=<user> --script=<script name only> --perm

# 사용자 폴더에서 다음 위치를 확인
#    ~/.config/os.helios.postlogonconfig/queue

# 위 폴더에서 각 파일이 다음 위치에 심볼릭 링크인지 확인
#    /usr/share/os.helios.postlogonconfig/scripts

import os
import sys
ORIG_SCRIPT_PATH: str = "/usr/share/os.helios.postlogonconfig/scripts/"
QUEUE_PATH: str = os.path.expanduser("~/.config/os.helios.postlogonconfig/queue/")
QUEUE_PERM_PATH: str = os.path.expanduser("~/.config/os.helios.postlogonconfig/perm/")

def exec_config():
    # queue 폴더에서 각 파일이 ORIG_SCRIPT_PATH에 심볼릭 링크인지 확인

    def run(queue_path: str, entry_name: str):
        entry_path: str = os.path.join(queue_path, entry_name)

        # 링크 확인
        if os.path.islink(entry_path):
            target_path = os.readlink(entry_path)

            # 링크가 맞다면 실행
            if target_path == ORIG_SCRIPT_PATH + entry_name:
                print(f"Executing {entry_name}...")
                os.system(target_path)

            # 링크가 아니면 실행 안함
            else:
                print(f"Warning: {entry_name} is a symbolic link but points to {target_path} instead of {ORIG_SCRIPT_PATH + entry_name}. Skipping.")
        else:
            print(f"Warning: {entry_name} is not a symbolic link. Skipping.")


    for entry in os.listdir(QUEUE_PATH):
        run(QUEUE_PATH, entry)
        os.remove(os.path.join(QUEUE_PATH, entry)) # 실행 후 큐에서 제거 (성공 여부와 상관없이 제거)

    for entry in os.listdir(QUEUE_PERM_PATH):
        run(QUEUE_PERM_PATH, entry)


def add_queue():
    # parameter 에서 --user=<user> --script=<script name only> --perm 추출
    user = None
    script = None
    is_perm = False
    sys_args = sys.argv[1:]
    for arg in sys_args:
        if arg.startswith("--user="):
            user = arg.split("=", 1)[1]
        elif arg.startswith("--script="):
            script = arg.split("=", 1)[1]
        elif arg == "--perm":
            is_perm = True

    if user is None:
        print("Error: --user parameter is required.")
        return
    if script is None:
        print("Error: --script parameter is required.")
        return

    # 심볼릭 링크 생성
    if not script.endswith(".sh"):
        script += ".sh"
    target_script_path = ORIG_SCRIPT_PATH + script
    if not os.path.isfile(target_script_path):
        print(f"Error: Script {target_script_path} does not exist.")
        return

    # perm / temp 위치 설정
    if is_perm:
        target_script_path = os.path.join(QUEUE_PERM_PATH, script)
    else:
        target_script_path = os.path.join(QUEUE_PATH, script)

    # 링크가 이미 있다면 링크 안만들기
    link_path = os.path.join(target_script_path, script)
    if os.path.exists(link_path):
        print(f"Warning: {link_path} already exists. Skipping.")
        return

    # 링크 만들기
    os.makedirs(target_script_path, exist_ok=True)
    os.symlink(target_script_path, link_path)
    print(f"Added {script} to {user}'s post logon config queue.")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        exec_config()
    else:
        add_queue()
