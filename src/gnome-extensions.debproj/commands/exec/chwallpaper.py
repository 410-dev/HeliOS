#!/usr/bin/env python3

# Usage
# chwallpaper <username> <picture path> [--no-copy-to-home] [--no-dark-mode-suffix] [--dark | --light]

import sys
import os
import shutil
import libpydbus

# 프로필 사진 사본 만들기 (.face)
def copy_profile_picture_to_face(username: str, image: str) -> str:
    target_dir = f"/home/{username}/.local/share/wallpapers"
    shutil.copyfile(image, target_dir)
    shutil.chown(image, user=username, group=username)
    return image


def get_paired_wallpaper_path(no_darkmode_suffix: bool, image: str, theme_mode: str|None) -> tuple[str|None, str|None]: # returns (light, dark)

    # If no_darkmode_suffix is set, we assume the same image is used for both light and dark mode
    if no_darkmode_suffix:
        return image, image

    if theme_mode == "dark":
        return None, image
    elif theme_mode == "light":
        return image, None

    pairs = (
        ["-light", "-dark"],
        ["_Light", "_Dark"],
    )

    # Check for paired wallpaper with _Light / _Dark suffix
    base, ext = os.path.splitext(image)
    for pair in pairs:
        light_suffix = pair[0]
        dark_suffix = pair[1]
        if base.endswith(light_suffix):
            base = base[:-len(light_suffix)]
        elif base.endswith(dark_suffix):
            base = base[:-len(dark_suffix)]
        light_path = f"{base}{light_suffix}{ext}"
        dark_path = f"{base}{dark_suffix}{ext}"
        if os.path.exists(light_path) and os.path.exists(dark_path):
            return light_path, dark_path

    return image, image


def main():
    if len(sys.argv) < 3:
        print("Usage: chwallpaper <username> <picture path> [--no-copy-to-home] [--no-dark-mode-suffix] [--dark | --light]")
        print("   --no-copy-to-home: Do not copy the image to user's home directory. Automatically triggers if the image is already in a shared location: /usr/share/backgrounds/")
        print("   --no-dark-mode-suffix: Do not look for paired wallpaper with _light/_dark suffixes. Use the same image for both modes.")
        print("   --dark: Set the image only for dark mode. May not use with --light")
        print("   --light: Set the image only for light mode. May not use with --dark")
        return 0

    username = sys.argv[1]
    picture_path = sys.argv[2]
    no_copy_to_home: bool = '--no-copy-to-home' in sys.argv or picture_path.startswith("/usr/share/backgrounds/")
    no_darkmode_suffix: bool = '--no-dark-mode-suffix' in sys.argv
    theme_mode: str | None = "dark" if "--dark" in sys.argv else "light" if "--light" in sys.argv else None

    # Check if theme mode conflicts
    if '--dark' in sys.argv and '--light' in sys.argv:
        theme_mode: str | None = None

    updated_picture_path = picture_path
    if not no_copy_to_home:
        updated_picture_path = copy_profile_picture_to_face(username, picture_path)

    # Dark mode check
    light_wallpaper, dark_wallpaper = get_paired_wallpaper_path(no_darkmode_suffix, updated_picture_path, theme_mode)

    try:
        if light_wallpaper:
            libpydbus.gsettings_set("org.gnome.desktop.background", "picture-uri", f"file://{light_wallpaper}", as_user=username)
        if dark_wallpaper:
            libpydbus.gsettings_set("org.gnome.desktop.background", "picture-uri-dark", f"file://{dark_wallpaper}", as_user=username)
        return 0
    except Exception as e:
        print(e)
    return 1

if __name__ == "__main__":
    sys.exit(main())
