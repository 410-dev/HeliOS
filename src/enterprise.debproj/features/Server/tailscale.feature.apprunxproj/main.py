import sys
from oscore.installer import Installer, PackagerSource
from AppContext import AppContext

context = AppContext()
context.ensure_single_process_globally()
context.ensure_privileged()

def compatibility():
    pass

def main(args: list[str]) -> int:
    compatibility()

    installer = Installer(context.id(), True, "apt")
    installer.raise_on_error()
    if "enable" in args:
        ubuntu_distro: str = "resolute"

        tailscale_source: PackagerSource = PackagerSource("tailscale")
        tailscale_source.signed = True
        tailscale_source.repo_url_path = f"https://pkgs.tailscale.com/stable/ubuntu/{ubuntu_distro}.tailscale-keyring.list"
        tailscale_source.keyring_path = "/usr/share/keyrings/tailscale-archive-keyring.gpg"
        tailscale_source.download_keyring(f"https://pkgs.tailscale.com/stable/ubuntu/{ubuntu_distro}.noarmor.gpg")

        installer.add_packager_source(tailscale_source)
        installer.refresh_sources()
        installer.install_package(["tailscale"])
        installer.commit_receipt()

        return 0
    elif "disable" in args:
        installer.revert()
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
