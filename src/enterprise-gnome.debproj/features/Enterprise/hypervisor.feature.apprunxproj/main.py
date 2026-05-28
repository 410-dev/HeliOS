import subprocess
import sys
import oscore.libuser as libuser
from oscore.installer import Installer
from AppContext import AppContext

context = AppContext()
context.ensure_single_process_globally()
context.ensure_privileged()

def compatibility():
    cmd = ["lscpu"]
    look_for = "Virtualization"
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        stdout, stderr = proc.communicate()
        print(stdout)
        if stdout is not None and look_for in stdout:
            print(f"[+] Virtualization support found.")
            return True
        else:
            print(f"[-] Virtualization support not available.")
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"[-] Command failed: {e}")
        sys.exit(1)

def main(args: list[str]) -> int:
    compatibility()

    installer = Installer(context.id(), True, "apt")
    installer.raise_on_error()
    if "enable" in args:
        installer.refresh_sources()
        installer.install_package(["qemu-system-x86", "libvirt-daemon-system", "libvirt-clients", "virtinst", "virt-manager", "bridge-utils"])

        users: list[str] = libuser.list_nosys_users()
        for user in users:
            installer.exec_shell(["usermod", "-aG", "libvirt", user], ["usermod", "-G", "libvirt", user])
            installer.exec_shell(["usermod", "-aG", "kvm", user], ["usermod", "-G", "kvm", user])

        installer.exec_shell(["systemctl", "enable", "--now", "libvirtd"], ["systemctl", "disable", "--now", "libvirtd"])
        installer.commit_receipt()

        return 0
    elif "disable" in args:
        installer.revert()
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
