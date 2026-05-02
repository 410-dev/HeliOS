import sys
from oscore.installer import Installer
from AppContext import AppContext

context = AppContext()
context.ensure_single_process_globally()
context.ensure_privileged()

def main(args: list[str]) -> int:
    installer = Installer("os.helios.feature.flatpak", True, "apt")
    installer.raise_on_error()
    if "enable" in args:
        installer.refresh_sources()
        installer.install_package(["flatpak"])
        installer.install_package(["gnome-software-plugin-flatpak"])
        installer.add_packager_source("flathub", "https://flathub.org/repo/flathub.flatpakrepo", "", "flatpak")
        installer.commit_receipt()
        return 0
    elif "disable" in args:
        installer.revert()
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
