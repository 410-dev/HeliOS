#!/usr/bin/env python3

# Usage
#   feature enable <feature name> [--experimental] - Enable a feature
#   feature disable <feature name> - Disable a feature
#   feature list - List all available features

import os
import sys
import subprocess

from oscore import libreg

FEATURES_DIR = [
    "{{FEATURES}}"
]

# Check if the user is root
def chk_root() -> bool:
    return os.geteuid() == 0


def get_features() -> tuple[dict[str, bool], dict[str, str]]:
    blacklisted: list = libreg.read("HKEY_LOCAL_MACHINE/SYSTEM/Policies/Features/Blacklisted", [])

    # Iterate through all features in the features directory
    features: dict[str, bool] = {}
    feature_paths: dict[str, str] = {}
    for features_dir in FEATURES_DIR:
        if not os.path.exists(features_dir):
            continue

        # Recursive, it is bundle only if enable.sh file exists in the directory. Traverse all directories in features_dir, and check if enable.sh file exists. If it does, it is a feature bundle, and the name of the feature is the name of the directory.
        for root, dirs, files in os.walk(features_dir):

            # Show xxx/yyy/feature_name, not just basename
            feature = os.path.relpath(root, features_dir)
            if feature in blacklisted:
                continue

            if not "enable.sh" in files: # enable.sh 파일이 없는 디렉토리는 기능 번들이 아니다.
                continue

            enabled = libreg.read(f"HKEY_LOCAL_MACHINE/SYSTEM/Features/{feature}/Enabled", False)

            features[feature] = enabled
            feature_paths[feature] = os.path.join(features_dir, feature)

    return features, feature_paths


def get_feature(feature: str) -> dict | None:
    for features_dir in FEATURES_DIR:
        feature_path = os.path.join(features_dir, feature)
        if os.path.exists(feature_path):
            return {
                "name": feature,
                "path": feature_path,
                "experimental": os.path.exists(os.path.join(feature_path, "ExperimentalFeature")),
                "enabled": libreg.read(f"HKEY_LOCAL_MACHINE/SYSTEM/Features/{feature}/Enabled", False)
            }
    return None


def enable_feature(feature: str, trigger_only: bool, one_way_enable: bool, experimental: bool, skip_compatibility_check: bool, no_interaction: bool) -> bool:
    if not chk_root():
        print("You must be root to enable a feature.")
        return False

    bundle_info: dict | None = get_feature(feature)

    # 활성화 가능 여부 체크
    if bundle_info is None:
        print(f"Feature '{feature}' does not exist.")
        return False

    if bundle_info["enabled"] and not trigger_only:
        print(f"Feature '{feature}' is already enabled.")
        return True

    # disable.sh 파일이 없다면 활성화할 수 없다.
    if not os.path.exists(os.path.join(bundle_info["path"], "disable.sh")) and not one_way_enable:
        print(f"Feature '{feature}' cannot be enabled because it does not have a disable.sh file. Use the --one-way-enablement flag to enable it anyway, but be aware that it cannot be disabled once enabled.")
        return False

    # 호환성 체크
    if not skip_compatibility_check:
        compatibility_script = os.path.join(bundle_info["path"], "compatibility.sh")
        if os.path.exists(compatibility_script):
            result = subprocess.run([compatibility_script])
            if result.returncode != 0:
                print(f"Feature '{feature}' is not compatible with the current system.")
                print("Compatibility check output:")
                print(result.stdout)
                print(result.stderr)
                return False
            
    # 실험적 기능 체크
    if bundle_info["experimental"] and not experimental:
        print(f"Feature '{feature}' is marked as experimental. Use the --experimental flag to enable it.")
        return False

    # 활성화
    enable_script = os.path.join(bundle_info["path"], "enable.sh")
    result = None
    if os.path.exists(enable_script):
        result = subprocess.run([enable_script, bundle_info["path"]])
        if result.returncode != 0 and result.returncode != 100: # 100은 재시동 요청
            print(f"Failed to enable feature '{feature}'.")
            print("Enable script output:")
            print(result.stdout)
            print(result.stderr)
            return False
    else:
        print(f"Feature '{feature}' does not have an enable.sh script. Marking as enabled without running any script.")

    if result is not None and result.returncode == 100:
        print(f"Feature '{feature}' enabled successfully. Please restart your system to apply the changes.")
        # 환경 변수의 DISPLAY 값이 존재한다면 재시동을 요청하는 메시지를 zenity 로 띄운다.
        if "DISPLAY" in os.environ:
            subprocess.run(["zenity", "--question", "--title=System Restart Required", "--text=Feature '{}' has been enabled. A system restart is required for changes to take effect.\n\nWould you like to restart now?".format(feature), "--width=400"])
            if result.returncode == 0:
                subprocess.run(["systemctl", "reboot"])
            else:
                print("Please remember to restart your system later.")

        # CLI 환경이라면, 재시동을 요청하는 메시지를 출력한다.
        elif not no_interaction:
            u_in = input(f"Feature '{feature}' enabled successfully. A system restart is required for changes to take effect.\n\nWould you like to restart now? (y/N): ")
            if u_in.lower() == "y":
                subprocess.run(["systemctl", "reboot"])
            else:
                print("Please remember to restart your system later.")
    else:
        libreg.write("root", f"HKEY_LOCAL_MACHINE/SYSTEM/Features/{feature}/Enabled", True)

    return True
    
def disable_feature(feature: str, trigger_only: bool) -> bool:
    if not chk_root():
        print("You must be root to disable a feature.")
        return False

    bundle_info: dict | None = get_feature(feature)

    if bundle_info is None:
        print(f"Feature '{feature}' does not exist.")
        return False

    if not bundle_info["enabled"] and not trigger_only:
        print(f"Feature '{feature}' is already disabled.")
        return True

    disable_script = os.path.join(bundle_info["path"], "disable.sh")
    result = None
    if os.path.exists(disable_script):
        result = subprocess.run([disable_script])
        if result.returncode != 0 and result.returncode != 100: # 100은 재시동 요청
            print(f"Failed to disable feature '{feature}'.")
            print("Disable script output:")
            print(result.stdout)
            print(result.stderr)
            return False
    else:
        print(f"Feature '{feature}' does not have a disable.sh script. Marking as disabled without running any script.")
    
    libreg.write("root", f"HKEY_LOCAL_MACHINE/SYSTEM/Features/{feature}/Enabled", False)

    if result is not None and result.returncode == 100:
        print(f"Feature '{feature}' disabled successfully. Please restart your system to apply the changes.")
        # 환경 변수의 DISPLAY 값이 존재한다면 재시동을 요청하는 메시지를 zenity 로 띄운다.
        if "DISPLAY" in os.environ:
            subprocess.run(["zenity", "--question", "--title=System Restart Required", "--text=Feature '{}' has been disabled. A system restart is required for changes to take effect.\n\nWould you like to restart now?".format(feature), "--width=400"])
            if result.returncode == 0:
                subprocess.run(["systemctl", "reboot"])
            else:
                print("Please remember to restart your system later.")

        # CLI 환경이라면, 재시동을 요청하는 메시지를 출력한다.
        else:
            u_in = input(f"Feature '{feature}' disabled successfully. A system restart is required for changes to take effect.\n\nWould you like to restart now? (y/N): ")
            if u_in.lower() == "y":
                subprocess.run(["systemctl", "reboot"])
            else:
                print("Please remember to restart your system later.")

    return True

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  feature enable <feature name> [--experimental] [--trigger-only] [--one-way-enablement] [--skip-compatibility-check] - Enable a feature")
        print("  feature disable <feature name> [--trigger-only] - Disable a feature")
        print("  feature list - List all available features")
        return

    command = sys.argv[1]

    if command == "list":
        features, _ = get_features()
        if not features:
            print("No features available.")
            return

        for feature, enabled in features.items():
            status = "*" if enabled else ""
            print(f"{status}{feature}")

    elif command == "enable":
        if len(sys.argv) < 3:
            print("Please specify a feature to enable.")
            return
        
        feature_name = sys.argv[2]
        experimental = "--experimental" in sys.argv
        trigger_only = "--trigger-only" in sys.argv
        one_way_enable = "--one-way-enablement" in sys.argv
        skip_compatibility_check = "--skip-compatibility-check" in sys.argv
        no_interaction = "--no-interaction" in sys.argv

        enable_feature(feature_name, trigger_only, one_way_enable, experimental, skip_compatibility_check, no_interaction)

    elif command == "disable":
        if len(sys.argv) < 3:
            print("Please specify a feature to disable.")
            return
        
        feature_name = sys.argv[2]
        trigger_only = "--trigger-only" in sys.argv
        disable_feature(feature_name, trigger_only)

    else:
        print(f"Unknown command '{command}'.")
        print("Usage:")
        print("  feature enable <feature name> [--experimental] [--trigger-only] [--one-way-enablement] [--skip-compatibility-check] - Enable a feature")
        print("  feature disable <feature name> [--trigger-only] - Disable a feature")
        print("  feature list - List all available features")


if __name__ == "__main__":
    main()
    