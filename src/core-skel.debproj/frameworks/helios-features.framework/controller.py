#!/usr/bin/env python3
import os
import subprocess
import sys
import oscore.libuser as libuser
from oscore.libjson5 import load
from oscore.libconfig import Config

# Usage
# $0 add-source | remove-source | update-repository

source_path: str = "/etc/apt/sources.list.d/helios-feature.list"
repo_path: str = "{{features}}"

# Require sudo
if not libuser.is_current_user_privileged_as_admin():
    print(f"This script must be run as root or should be privileged as administrator group ({libuser.GROUP_Administrator()}).")
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

def enable():
    feature_name: str = sys.argv[2] if len(sys.argv) > 2 else None
    if feature_name is None:
        print("[-] Feature name is required for enable command.")
        print_usage()
        exit(1)

    # If apprunx file exists, then it is not so simple as installing local package.
    # If toml file, then read it and install the packages.
    apprunx_path: str = f"{repo_path}/{feature_name}.feature.apprunx"
    if not os.path.isfile(apprunx_path):
        print(f"[-] Feature package not found: {feature_name}")
        exit(1)

    # Read registry
    config: Config = Config("os.helios.features.EnabledList", enforce_global=True).fetch()

    # Check if feature is already enabled
    if feature_name in config.keys() and config.get(feature_name).get("enabled") == True:
        print(f"[-] Feature already enabled: {feature_name}")
        exit(1)

    print(f"[*] Enabling feature (apprunx mode): {feature_name}")
    try:
        result = subprocess.run(["apprun", apprunx_path, "enable"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"[-] Command failed: {e}")
        print(f"Subprocess produced:")
        if result is None:
            print("Nothing")
        else:
            print("====stdout====")
            print(f"{result.stdout.decode('utf-8')}")
            print("")
            print("====stderr====")
            print(f"{result.stderr.decode('utf-8')}")
        exit(1)

    if result.returncode == 0:
        print(f"[+] Feature enabled: {feature_name}")
    else:
        print(f"[-] Failed to enable feature: {feature_name}")
        exit(1)

    config_dat = config.get(feature_name, {})
    config_dat.update({"enabled": True})
    config[feature_name] = config_dat
    config.sync()

def disable():
    feature_name: str = sys.argv[2] if len(sys.argv) > 2 else None
    if feature_name is None:
        print("[-] Feature name is required for enable command.")
        print_usage()
        exit(1)

    # If apprunx file exists, then it is not so simple as installing local package.
    # If toml file, then read it and install the packages.
    apprunx_path: str = f"{repo_path}/{feature_name}.feature.apprunx"

    if not os.path.isfile(apprunx_path):
        print(f"[-] Feature package not found: {feature_name}")
        exit(1)


    # Read registry
    config: Config = Config("os.helios.features.EnabledList", enforce_global=True).fetch()

    # Check if feature is already enabled
    if feature_name not in config.keys() or config.get(feature_name).get("enabled") != True:
        print(f"[-] Feature already disabled: {feature_name}")
        exit(1)

    print(f"[*] Disabling feature (apprunx mode): {feature_name}")
    result = subprocess.run(["apprun", apprunx_path, "disable"], check=True)
    if result.returncode == 0:
        print(f"[+] Feature disabled: {feature_name}")
    else:
        print(f"[-] Failed to disable feature: {feature_name}")
        exit(1)

    config_dat = config.get(feature_name, {})
    config_dat.update({"enabled": False})
    config[feature_name] = config_dat
    config.sync()


def list_features():
    # Two sections
    #   {repo_path}/_index/*.json5    (Merge update all files)
    #
    # For index files, it should contain an array named "expose".

    index_features: dict = {}
    locale: str = os.environ.get("LOCALE", "en").lower()[:2] # Get only first two characters

    for entry in os.listdir(os.path.join(repo_path, "_index")):
        if entry.endswith(".json5"):
            dat: dict = load(os.path.join(repo_path, "_index", entry))
            index_features.update(dat)

    print_index: int = 1
    print("[*] Available features:")

    # Read registry
    config: Config = Config("os.helios.features.EnabledList", enforce_global=True).fetch()
    enabled_features = {key for key, value in config.items() if value.get("enabled") == True}

    for feature_name in sorted(set(index_features.get("expose", []))):
        status: str = "Enabled" if feature_name in enabled_features else "Disabled"

        description = index_features.get("description", {}).get(feature_name, {}).get(locale, "")

        if len(description) > 0:
            description = f": {description}"

        print(f"  {print_index}. {feature_name} [{status}]{description}")
        print_index += 1

def print_usage():
    script = os.path.basename(sys.argv[0])
    print(f"Usage: {script} <command>")
    print("Commands:")
    print("  add-source         Add APT source entry")
    print("  remove-source      Remove APT source entry")
    print("  update-repository  Rebuild package index and run apt update")
    print("  enable             Enable feature")
    print("  disable            Disable feature")
    print("  list               List all features")

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
    case "enable":
        enable()
    case "disable":
        disable()
    case "list":
        list_features()
    case _:
        print(f"[-] Unknown command: {command}")
        print_usage()
        exit(1)