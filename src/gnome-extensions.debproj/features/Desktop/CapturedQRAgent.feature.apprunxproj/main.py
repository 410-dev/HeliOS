import sys
from oscore.installer import Installer, PackagerSource
from AppContext import AppContext

context = AppContext()
context.ensure_single_process_globally()
context.ensure_privileged()

def main(args: list[str]) -> int:
    installer = Installer("os.helios.feature.capturedqragent", True, "apt")
    installer.raise_on_error()
    if "enable" in args:
        installer.log("Creating symbolic link to applications...")
        installer.symlink("{{frameworks}}/CapturedQRAgents/control-app.apprunx", "/applications/CapturedQRAgents Control Panel.apprunx")
        installer.log("Installing global user service...")
        installer.exec_shell_with_exit_code(["apprun", "--install-as-global-user-service=simple,graphical-session.target", "{{frameworks}}/CapturedQRAgents/daemon.apprunx"],
                                            ["apprun", "--uninstall-as-global-user-service", "{{frameworks}}/CapturedQRAgents/daemon.apprunx"])
        installer.log("Done.")
        installer.commit_receipt()
        return 0
    elif "disable" in args:
        installer.revert()
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
