#!/usr/bin/env python3
import os
import subprocess
import sys

# Usage
# $0 add-source | remove-source | update-repository

source_path: str = "/etc/apt/sources.list.d/helios-feature.list"
repo_path: str = "{{features}}"

# Require sudo
if not os.geteuid() == 0:
    print("This script must be run as root.")
    exit(1)

def add_source():
    content: str = f"deb [trusted=yes] file:{repo_path} ./\n"
    with open(source_path, "w") as fout:
        fout.write(content)
    print(f"[+] APT source added: {source_path}")

def remove_source():
    if os.path.exists(source_path):
        os.remove(source_path)
        print(f"[+] APT source removed: {source_path}")
    else:
        print(f"[-] Source file not found: {source_path}")

def update_repository():
    # Packages.gz 인덱스 재생성
    if not os.path.isdir(repo_path):
        print(f"[-] Repository path not found: {repo_path}")
        exit(1)

    print("[*] Generating package index...")
    packages_path = os.path.join(repo_path, "Packages")

    try:
        # Packages 파일 생성
        with open(packages_path, "w") as fout:
            subprocess.run(
                ["dpkg-scanpackages", "--multiversion", "."],
                cwd=repo_path,
                stdout=fout,
                stderr=subprocess.PIPE,
                check=True
            )

        # Packages.gz 생성
        with open(packages_path, "rb") as fin, \
             open(packages_path + ".gz", "wb") as fout:
            subprocess.run(
                ["gzip", "-9c"],
                stdin=fin,
                stdout=fout,
                check=True
            )

        print("[+] Package index updated.")

        # apt update 실행
        print("[*] Running apt update...")
        subprocess.run(["apt-get", "update"], check=True)
        print("[+] apt update complete.")

    except subprocess.CalledProcessError as e:
        print(f"[-] Command failed: {e}")
        exit(1)
    except FileNotFoundError as e:
        print(f"[-] Required tool not found: {e}")
        print("    Try: sudo apt install dpkg-dev")
        exit(1)

def print_usage():
    script = os.path.basename(sys.argv[0])
    print(f"Usage: {script} <command>")
    print("Commands:")
    print("  add-source         Add APT source entry")
    print("  remove-source      Remove APT source entry")
    print("  update-repository  Rebuild package index and run apt update")

# Main
if len(sys.argv) < 2:
    print_usage()
    exit(1)

command = sys.argv[1]

match command:
    case "add-source":
        add_source()
    case "remove-source":
        remove_source()
    case "update-repository":
        update_repository()
    case _:
        print(f"[-] Unknown command: {command}")
        print_usage()
        exit(1)