import subprocess
import sys
import oscore.libuser as libuser
from oscore.installer import Installer
from AppContext import AppContext

context = AppContext()
context.ensure_single_process_globally()
context.ensure_privileged()

def main(args: list[str]) -> int:

    installer = Installer(context.id(), True, "apt")
    installer.raise_on_error()
    if "enable" in args:
        installer.refresh_sources()
        installer.install_package(["timeshift"])
        installer.commit_receipt()

        return 0
    elif "disable" in args:
        installer.revert()
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
