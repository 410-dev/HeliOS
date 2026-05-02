import os
import shutil
import subprocess
import json
import time
import oscore.libatomic as libatomic
import tempfile
import requests

class PackagerSource:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.trusted = False
        self.signed = False
        self.keyring_path = None
        self.repo_url_path = None
        self.scope = None

    def _invoke_add_source(self, packager: str) -> bool:
        if packager == "apt":
            with open(f"/etc/apt/sources.list.d/{self.name}.list", "w") as fout:
                fout.write(self._apt_string())
            return True
        elif packager == "flatpak":
            subprocess.run(["flatpak", "remote-add", "--if-not-exists", self.name, self.repo_url_path], check=True)
            return True

        return False

    def _apt_string(self) -> str:
        if self.repo_url_path is None:
            raise ValueError("Repository path is not set.")
        return f"deb [{'trusted=yes ' if self.trusted else ''}{'signed-by=' + self.keyring_path if self.signed and self.keyring_path else ''}] {self.repo_url_path} {self.scope}\n"

    def download_keyring(self, keyring_url: str) -> bool:
        if self.keyring_path is None:
            raise ValueError("Keyring path is not set.")

        try:
            response = requests.get(keyring_url)
            response.raise_for_status()
            with open(self.keyring_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"Failed to download keyring: {e}")
            return False

class Installer:

    def __init__(self, package_id: str, require_root: bool, default_packager: str, total_processes: int = 0, raise_on_error: bool = True):

        if require_root:
            if not os.geteuid() == 0:
                raise PermissionError("This installer must be run as root.")

        self.package_id = package_id
        self.default_packager = default_packager
        self.total_processes = total_processes
        self.commit_path = f"/var/lib/oscore/receipts/{self.package_id}"
        self._process: list[dict] = []
        self._logs: dict[int, str] = {}
        self._raise_on_error = raise_on_error

        self._packager_commandlines: dict[str, dict[str, list[str]]] = {
            "apt": {
                "refresh": ["apt", "update"],
                "install": ["apt", "install", "-y"],
                "remove": ["apt", "remove", "-y"]
            },
            "flatpak": {
                "refresh": [],
                "install": ["flatpak", "install", "-y"],
                "remove": ["flatpak", "uninstall", "-y"]
            },
            "snap": {
                "refresh": ["snap", "refresh"],
                "install": ["snap", "install", "-y"],
                "remove": ["snap", "remove", "-y"]
            }
        }

    def raise_on_error(self, set_to: bool = True):
        self._raise_on_error = set_to

    def log(self, message: str) -> None:
        self._logs[len(self._process)] = message
        print(message)

    def _handle_exit(self, success: bool, message: str) -> bool | None:
        if not success and self._raise_on_error:
            raise Exception(message)
        else:
            return success

    def _exec_instruct(self, packager: str, instruction: str, packages: list[str] = None, expected_exit_code: int = 0) -> bool:

        # Packager None = Default
        if packager is None:
            packager = self.default_packager

        cmd = self._packager_commandlines.get(packager, {}).get(instruction, [])
        if cmd:
            if packages is not None:
                cmd.extend(packages)

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._process.append({
                "type": "packager",
                "packager": packager,
                "instruction": instruction,
                "packages": packages if packages is not None else [],
                "result": result.returncode,
                "message": "executed"
            })
            return self._handle_exit(result.returncode == expected_exit_code, f"Failed to execute packager command: {packager}. Output: {result.stdout}, Error: {result.stderr}")

        else:
            print(f"Instruction '{instruction}' is not supported for packager: {packager}")
            self._process.append({
                "type": "packager",
                "packager": packager,
                "instruction": instruction,
                "packages": packages if packages is not None else [],
                "result": -1,
                "message": "unsupported"
            })
            return self._handle_exit(False, f"Failed to execute packager command: {packager}")

    def install_package(self, packages: list[str], packager: str = None, expected_exit_code: int = 0) -> bool:
        return self._exec_instruct(packager, "install", packages, expected_exit_code=expected_exit_code)

    def uninstall_package(self, packages: list[str], packager: str = None, expected_exit_code: int = 0) -> bool:
        return self._exec_instruct(packager, "remove", packages, expected_exit_code=expected_exit_code)

    def refresh_sources(self, packager: str = None, expected_exit_code: int = 0) -> bool:
        return self._exec_instruct(packager, "refresh", expected_exit_code=expected_exit_code)

    def add_packager_source(self, repo: PackagerSource, packager: str = None) -> bool:
        if packager is None:
            packager = self.default_packager

        try:
            result = repo._invoke_add_source(packager)

            self._process.append({
                "type": "packager-source",
                "packager": packager,
                "instruction": "add",
                "result": result,
                "message": "added"
            })

        except Exception as e:
            print(f"Failed to add packager source: {e}")
            result = False
            self._process.append({
                "type": "packager-source",
                "packager": packager,
                "instruction": "add",
                "result": result,
                "message": f"Failed to add packager source: {e}"
            })

        return self._handle_exit(result, f"Adding packager source is not implemented yet: {repo.repo_url_path} for {packager}")

    def symlink(self, target: str, link_name: str) -> bool:
        if os.path.exists(link_name):
            os.remove(link_name)
        try:
            os.symlink(target, link_name)
            self._process.append({
                "type": "symlink",
                "source": link_name,
                "destination": link_name
            })
            return True
        except OSError:
            print(f"Failed to create symlink: {link_name} -> {target}")
            self._process.append({
                "type": "symlink",
                "source": link_name,
                "destination": target,
                "result": -1,
                "message": "failed"
            })
            return self._handle_exit(False, f"Failed to create symlink: {link_name} -> {target}")

    def _file_ops(self, instruction: str, source: str, destination: str | None) -> bool:
        is_directory = False
        if instruction == "copy":
            if os.path.isdir(destination):
                is_directory = True
                shutil.copytree(destination, source)
            else:
                shutil.copy2(source, destination)
        elif instruction == "move":
            if os.path.isdir(source):
                is_directory = True
            shutil.move(source, destination)
        elif instruction == "remove":
            if os.path.isdir(source):
                is_directory = True
                shutil.rmtree(source)
            else:
                os.remove(source)
        else:
            print(f"Unsupported file operation: {instruction}")
            return self._handle_exit(False, f"Unsupported file operation: {instruction}")

        self._process.append({
            "type": "file_ops",
            "instruction": instruction,
            "source": source,
            "destination": destination if destination is not None else "",
            "is_directory": is_directory
        })
        return True

    def copy(self, source: str, destination: str) -> bool:
        return self._file_ops("copy", source, destination)

    def move(self, source: str, destination: str) -> bool:
        return self._file_ops("move", source, destination)

    def remove(self, path: str) -> bool:
        return self._file_ops("remove", path, None)

    def string_ops(self, instruction: str, file_path: str, old_str: str | None = None, new_str: str | None = None) -> bool:
        if instruction == "replace":
            if old_str is None or new_str is None:
                print("Both 'old_str' and 'new_str' must be provided for replace operation.")
                return self._handle_exit(False, f"Both 'old_str' and 'new_str' must be provided.")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                content = content.replace(old_str, new_str)
                libatomic.atomic_write(file_path, content)
                self._process.append({
                    "type": "string_ops",
                    "instruction": instruction,
                    "file_path": file_path,
                    "old_str": old_str,
                    "new_str": new_str
                })
                return True
            except Exception as e:
                print(f"Failed to perform string operation: {e}")
                self._process.append({
                    "type": "string_ops",
                    "instruction": instruction,
                    "file_path": file_path,
                    "old_str": old_str,
                    "new_str": new_str,
                    "result": -1,
                    "message": f"failed: {e}"
                })
                return self._handle_exit(False, f"Failed to perform string operation: {e}")

        elif instruction == "write":
            try:
                libatomic.atomic_write(file_path, new_str)
                self._process.append({
                    "type": "string_ops",
                    "instruction": instruction,
                    "file_path": file_path,
                    "new_str": new_str if new_str is not None else "",
                    "result": 0,
                    "message": "executed"
                })
                return True
            except Exception as e:
                print(f"Failed to perform string operation: {e}")
                self._process.append({
                    "type": "string_ops",
                    "instruction": instruction,
                    "file_path": file_path,
                    "new_str": new_str if new_str is not None else "",
                    "result": -1,
                    "message": f"failed: {e}"
                })
                return self._handle_exit(False, f"Failed to perform string operation: {e}")

        else:
            print(f"Unsupported string operation: {instruction}")
            return self._handle_exit(False, f"Unsupported string operation: {instruction}")

    def replace_string(self, file_path: str, old_str: str, new_str: str) -> bool:
        return self.string_ops("replace", file_path, old_str, new_str)

    def new_file(self, file_path: str, new_str: str | None = None) -> bool:
        return self.string_ops("write", file_path, None, new_str)

    def extract(self, archive_path: str, destination: str, compression: str = "zip") -> bool:
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()

            if compression == "zip":
                shutil.unpack_archive(archive_path, temp_dir, "zip")
            elif compression in ["tar", "gztar", "bztar", "xztar"]:
                shutil.unpack_archive(archive_path, temp_dir, compression)
            else:
                print(f"Unsupported compression format: {compression}")
                return self._handle_exit(False, f"Unsupported compression format: {compression}")

            # Build file list
            file_list: dict[str, str] = {} # destination merged file path is key, value is either file or dir
            for root, dirs, files in os.walk(temp_dir):
                for name in files:
                    file_path = os.path.join(root, name)
                    relative_path = os.path.relpath(file_path, temp_dir)
                    dest_path = os.path.join(destination, relative_path)
                    file_list[dest_path] = file_path
                for name in dirs:
                    dir_path = os.path.join(root, name)
                    relative_path = os.path.relpath(dir_path, temp_dir)
                    dest_path = os.path.join(destination, relative_path)
                    file_list[dest_path] = dir_path

            # Move files to destination
            for dest_path, src_path in file_list.items():
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dest_path)

            self._process.append({
                "type": "extract",
                "archive_path": archive_path,
                "destination": destination,
                "compression": compression,
                "files": list(file_list.keys()),
                "result": 0,
                "message": "executed"
            })
            return True
        except Exception as e:
            print(f"Failed to extract archive: {e}")
            self._process.append({
                "type": "extract",
                "archive_path": archive_path,
                "destination": destination,
                "compression": compression,
                "result": -1,
                "message": f"failed: {e}"
            })
            return self._handle_exit(False, f"Failed to extract archive: {e}")

    def exec_shell_with_exit_code(self, install_command: list[str], revert_command: list[str]) -> int:
        result = subprocess.run(install_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._process.append({
            "type": "shell",
            "install_command": install_command,
            "revert_command": revert_command,
            "result": result.returncode,
            "message": "executed"
        })
        return result.returncode

    def exec_shell(self, install_command: list[str], revert_command: list[str], expected_exit_code: int = 0) -> bool:
        result = self.exec_shell_with_exit_code(install_command, revert_command)
        return self._handle_exit(result == expected_exit_code, f"Failed to execute shell command: {' '.join(install_command)}. Exited: {result}")

    def progress(self) -> float:
        if self.total_processes == 0:
            return 0.0
        return len(self._process) / self.total_processes * 100.0

    def make_receipt(self, include_logs = False) -> list[dict]:
        receipt = []
        for idx, item in enumerate(self._process):
            entry = {
                "step": idx + 1,
                "type": item.get("type"),
                "details": {k: v for k, v in item.items() if k != "type"}
            }
            receipt.append(entry)
            if include_logs and self._logs.get(idx) is not None:
                log_message = self._logs.get(idx, "")
                if log_message:
                    receipt.append({
                        "step": idx + 1,
                        "type": "log",
                        "details": {
                            "message": log_message
                        }
                    })

        return receipt

    def commit_receipt(self) -> None:
        processes = self.make_receipt()
        receipt = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "package_id": self.package_id,
            "user": os.getenv("SUDO_USER") or os.getenv("USER") or "unknown",
            "euid": os.geteuid(),
            "processes": processes
        }
        os.makedirs(self.commit_path, exist_ok=True)
        with open(f"{self.commit_path}/{self.package_id}_receipt.json", "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=4)

    def revert(self) -> bool:
        # TODO - Read the receipt and revert the processes in reverse order
        return True
