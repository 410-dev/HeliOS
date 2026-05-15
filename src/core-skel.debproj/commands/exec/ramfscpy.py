#!/usr/bin/env python3
"""
ramfscpy: copy a regular file or directory into RAM-backed tmpfs and optionally
bind-mount it back onto the original path.

Linux-only. Requires: python3, rsync, mount/umount, sudo when not run as root.

Examples:
  ramfscpy mydoc
  ramfscpy mydoc/
  ramfscpy --xbuffer=0.1 --xbuffermin=64M myapp/
  ramfscpy --mount=/mnt/memfs myapp
  ramfscpy --silent --mount=/mnt/memfs myapp
  ramfscpy --verbose myapp
  ramfscpy status myapp
  ramfscpy sync myapp
  ramfscpy unmount myapp --sync

Output policy:
  - default mount success prints only the tmpfs mount point to stdout
  - --verbose prints progress to stderr; stdout remains the mount point only
  - --silent prints nothing; for mount it requires --mount so generated paths
    are not lost

Copy semantics:
  - regular file:     file.txt -> <mount>/file.txt
  - directory:        mydoc    -> <mount>/mydoc/...
  - trailing slash:   mydoc/   -> <mount>/...

Default behavior:
  - uses tmpfs, not raw ramfs
  - if --mount is omitted, uses /run/mnt/<user>/ramfscpy/<random8>
  - bind-mounts the RAM copy back onto the original path unless --no-bind is set
  - does NOT write changes back unless `sync` or `unmount --sync` is used
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

VERSION = "0.3.0"
DEFAULT_XBUFFER = 0.1
DEFAULT_XBUFFER_MIN = "64M"
STATE_VERSION = 1


class RamfsCpyError(RuntimeError):
    pass


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def die(message: str, code: int = 1) -> None:
    eprint(f"ramfscpy: error: {message}")
    raise SystemExit(code)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def require_command(name: str) -> None:
    if not has_command(name):
        die(f"required command not found: {name}")


def require_linux() -> None:
    if sys.platform != "linux":
        die("this implementation is Linux-only because it uses tmpfs and bind mounts")


def is_verbose(args: argparse.Namespace | None) -> bool:
    return bool(getattr(args, "verbose", False))


def is_silent(args: argparse.Namespace | None) -> bool:
    return bool(getattr(args, "silent", False))


def should_log(args: argparse.Namespace | None, *, dry_run: bool = False, force: bool = False) -> bool:
    if is_silent(args):
        return False
    return force or dry_run or is_verbose(args)


def log(message: str, args: argparse.Namespace | None = None, *, dry_run: bool = False, force: bool = False) -> None:
    if should_log(args, dry_run=dry_run, force=force):
        eprint(message)


def owner_uid_gid() -> tuple[int, int]:
    """Return the invoking user's uid/gid, even when executed via sudo."""
    uid = int(os.environ.get("SUDO_UID", os.getuid()))
    gid = int(os.environ.get("SUDO_GID", os.getgid()))
    return uid, gid


def invoking_user_name() -> str:
    uid, _gid = owner_uid_gid()
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._-")
    return sanitized or str(uid)


def invoking_home() -> Path:
    if "RAMFSCPY_STATE_DIR" in os.environ:
        return Path(os.environ["RAMFSCPY_STATE_DIR"]).expanduser().resolve().parent

    uid, _gid = owner_uid_gid()
    try:
        return Path(pwd.getpwuid(uid).pw_dir)
    except KeyError:
        return Path.home()


def state_dir() -> Path:
    if "RAMFSCPY_STATE_DIR" in os.environ:
        return Path(os.environ["RAMFSCPY_STATE_DIR"]).expanduser().resolve()

    if "XDG_STATE_HOME" in os.environ and "SUDO_UID" not in os.environ:
        return Path(os.environ["XDG_STATE_HOME"]).expanduser().resolve() / "ramfscpy"

    return invoking_home() / ".local" / "state" / "ramfscpy"


def make_state_dir(args: argparse.Namespace | None, *, dry_run: bool = False) -> Path:
    d = state_dir()
    if dry_run:
        log(f"+ mkdir -p {shlex.quote(str(d))}", args, dry_run=True)
        return d

    d.mkdir(parents=True, exist_ok=True)
    try:
        uid, gid = owner_uid_gid()
        os.chown(d, uid, gid)
    except PermissionError:
        pass
    return d


def run(
    cmd: list[str],
    *,
    sudo: bool = False,
    dry_run: bool = False,
    args: argparse.Namespace | None = None,
) -> None:
    full = cmd
    if sudo and os.geteuid() != 0:
        require_command("sudo")
        full = ["sudo", *cmd]

    log("+ " + shlex.join(full), args, dry_run=dry_run)
    if dry_run:
        return

    try:
        subprocess.run(full, check=True)
    except subprocess.CalledProcessError as exc:
        raise RamfsCpyError(f"command failed with exit code {exc.returncode}: {shlex.join(full)}") from exc


def capture(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RamfsCpyError(f"command failed: {shlex.join(cmd)}") from exc


_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtpe]?i?b?|b)?\s*$", re.IGNORECASE)


def parse_size(value: str) -> int:
    """
    Parse sizes like 64M, 64MiB, 1G, 500K, 1234.
    Bare K/M/G/T/P/E are treated as IEC units, so 1M == 1 MiB.
    """
    m = _SIZE_RE.match(value)
    if not m:
        raise argparse.ArgumentTypeError(f"invalid size: {value!r}")

    number = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    multipliers = {
        "": 1,
        "b": 1,
        "k": 1024,
        "kb": 1024,
        "ki": 1024,
        "kib": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "mi": 1024**2,
        "mib": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
        "gi": 1024**3,
        "gib": 1024**3,
        "t": 1024**4,
        "tb": 1024**4,
        "ti": 1024**4,
        "tib": 1024**4,
        "p": 1024**5,
        "pb": 1024**5,
        "pi": 1024**5,
        "pib": 1024**5,
        "e": 1024**6,
        "eb": 1024**6,
        "ei": 1024**6,
        "eib": 1024**6,
    }
    return int(math.ceil(number * multipliers[suffix]))


def parse_nonnegative_float(value: str) -> float:
    try:
        x = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float: {value!r}") from exc
    if x < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return x


def format_iec(num: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"]
    n = float(num)
    for unit in units:
        if abs(n) < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{num} B"


def raw_path_has_trailing_slash(raw: str) -> bool:
    stripped = raw.rstrip()
    return stripped not in {"", "/"} and stripped.endswith("/")


def resolve_existing_path(path: str) -> Path:
    p = Path(path).expanduser().resolve(strict=True)
    if p == Path("/"):
        die("refusing to operate on /")
    if not p.is_file() and not p.is_dir():
        die(f"not a regular file or directory: {p}")
    return p


def resolve_abs_path(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve(strict=False)


def source_type(path: Path) -> str:
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "file"
    die(f"not a regular file or directory: {path}")


def copy_mode_for(raw_path: str, src: Path, src_type: str) -> str:
    """
    Returns:
      - file:     copy the regular file as <mount>/<name>
      - self:     copy the directory itself as <mount>/<name>/...
      - contents: copy directory contents into <mount>/...
    """
    if src_type == "file":
        if raw_path_has_trailing_slash(raw_path):
            die(f"trailing slash was provided, but source is a file: {src}")
        return "file"
    return "contents" if raw_path_has_trailing_slash(raw_path) else "self"


def random_mountpoint() -> Path:
    base = Path("/run/mnt") / invoking_user_name() / "ramfscpy"
    for _ in range(128):
        candidate = base / secrets.token_hex(4)  # 8 lowercase hex chars
        if not candidate.exists():
            return candidate
    die(f"could not allocate a random mount point under {base}")


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def source_key(src: Path) -> str:
    return hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:16]


def state_path_for(src: Path) -> Path:
    return state_dir() / f"{source_key(src)}.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"no ramfscpy state found for path: {path}")
    except json.JSONDecodeError as exc:
        die(f"state file is corrupted: {path}: {exc}")


def write_json(path: Path, data: dict[str, Any], *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if dry_run:
        log(f"+ write state {shlex.quote(str(path))}", args, dry_run=True)
        log(text.rstrip(), args, dry_run=True)
        return

    path.write_text(text, encoding="utf-8")
    try:
        uid, gid = owner_uid_gid()
        os.chown(path, uid, gid)
    except PermissionError:
        pass


def get_path_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size

    if has_command("du"):
        try:
            out = capture(["du", "-sb", str(path)])
            return int(out.split()[0])
        except Exception:
            pass

    total = 0
    for root, dirs, files in os.walk(path):
        root_p = Path(root)
        try:
            total += root_p.lstat().st_size
        except OSError:
            pass
        for name in dirs + files:
            p = root_p / name
            try:
                total += p.lstat().st_size
            except OSError:
                pass
    return total


def calculate_tmpfs_size(used: int, xbuffer: float, xbuffermin: int, explicit_size: int | None) -> int:
    if explicit_size is not None:
        if explicit_size < used:
            die(f"--size {format_iec(explicit_size)} is smaller than source size {format_iec(used)}")
        return explicit_size

    extra = max(int(math.ceil(used * xbuffer)), xbuffermin)
    return used + extra


def ensure_dir_with_owner(path: Path, *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    uid, gid = owner_uid_gid()
    run(["mkdir", "-p", str(path)], sudo=True, dry_run=dry_run, args=args)
    run(["chown", f"{uid}:{gid}", str(path)], sudo=True, dry_run=dry_run, args=args)


def is_mountpoint(path: Path) -> bool:
    return path.exists() and os.path.ismount(path)


def mount_tmpfs(mountpoint: Path, size_bytes: int, *, dry_run: bool = False, args: argparse.Namespace | None = None) -> bool:
    """Mount tmpfs if needed. Returns True if this invocation mounted it."""
    if is_mountpoint(mountpoint):
        log(f"ramfscpy: using existing mount point: {mountpoint}", args)
        return False

    ensure_dir_with_owner(mountpoint, dry_run=dry_run, args=args)
    run(
        ["mount", "-t", "tmpfs", "-o", f"size={size_bytes}", "tmpfs", str(mountpoint)],
        sudo=True,
        dry_run=dry_run,
        args=args,
    )
    ensure_dir_with_owner(mountpoint, dry_run=dry_run, args=args)
    return True


def rsync_args(excludes: Iterable[str]) -> list[str]:
    args = ["rsync", "-aH", "--numeric-ids"]
    for pattern in excludes:
        args.extend(["--exclude", pattern])
    return args


def rsync_copy(src: Path, dest: Path, *, copy_mode: str, excludes: list[str], dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    require_command("rsync")
    if copy_mode == "contents":
        cmd = [*rsync_args(excludes), f"{src}/", f"{dest}/"]
    elif copy_mode == "self":
        cmd = [*rsync_args(excludes), f"{src}/", f"{dest}/"]
    else:
        cmd = [*rsync_args([]), str(src), str(dest)]
    run(cmd, dry_run=dry_run, args=args)


def rsync_sync(src: Path, dest: Path, *, copy_mode: str, excludes: list[str], dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    require_command("rsync")
    if copy_mode in {"contents", "self"}:
        cmd = [*rsync_args(excludes), "--delete", f"{src}/", f"{dest}/"]
    else:
        cmd = [*rsync_args([]), str(src), str(dest)]
    run(cmd, dry_run=dry_run, args=args)


def remove_path(path: Path, *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    if dry_run:
        if path.is_dir() and not path.is_symlink():
            log(f"+ rm -rf {shlex.quote(str(path))}", args, dry_run=True)
        else:
            log(f"+ rm -f {shlex.quote(str(path))}", args, dry_run=True)
        return

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def remove_placeholder(path: Path, src_type: str, *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    if dry_run:
        action = "rmdir" if src_type == "dir" else "rm -f"
        log(f"+ {action} {shlex.quote(str(path))}", args, dry_run=True)
        return

    if src_type == "dir":
        path.rmdir()
    else:
        path.unlink()


def default_backup_path(src: Path, key: str) -> Path:
    return src.parent / f".{src.name}.ramfscpy.orig-{key}"


def ram_copy_path(mountpoint: Path, src: Path, copy_mode: str) -> Path:
    if copy_mode == "contents":
        return mountpoint
    return mountpoint / src.name


def bind_source_path(mountpoint: Path, src: Path, copy_mode: str) -> Path:
    return ram_copy_path(mountpoint, src, copy_mode)


def check_destination_ready(dest: Path, copy_mode: str, *, force: bool) -> None:
    if copy_mode == "contents":
        if dest.exists() and dest.is_dir() and any(dest.iterdir()) and not force:
            die(f"mount point is not empty: {dest}; use --force only after verifying it is safe")
        return

    if dest.exists() and not force:
        if copy_mode == "self" and dest.is_dir() and not any(dest.iterdir()):
            return
        die(f"destination already exists: {dest}; use --force only after verifying it is safe")


def load_state_for_path(path_text: str) -> tuple[Path, Path, dict[str, Any]]:
    src = resolve_abs_path(path_text)
    sp = state_path_for(src)
    data = read_json(sp)
    if data.get("state_version") != STATE_VERSION:
        die(f"unsupported state file version in {sp}")
    return src, sp, data


def cmd_mount(args: argparse.Namespace) -> None:
    require_linux()

    mount_was_explicit = args.mount is not None
    if args.silent and not mount_was_explicit:
        die("--silent requires --mount; otherwise the generated mount point would be lost")

    raw_path = args.path
    src = resolve_existing_path(raw_path)
    src_type = source_type(src)
    copy_mode = copy_mode_for(raw_path, src, src_type)

    mountpoint = resolve_abs_path(args.mount) if mount_was_explicit else random_mountpoint()
    generated_mount = not mount_was_explicit
    key = source_key(src)
    sp = state_path_for(src)

    if sp.exists() and not args.force:
        die(f"state already exists for {src}; maybe already mounted? Try `ramfscpy status {src}`")

    if mountpoint == src or (src.is_dir() and is_relative_to(mountpoint, src)):
        die("--mount must not be the source path itself or inside the source directory")

    backup = default_backup_path(src, key)
    dest = ram_copy_path(mountpoint, src, copy_mode)
    bind_src = bind_source_path(mountpoint, src, copy_mode)

    if backup.exists() and not args.force:
        die(f"backup path already exists: {backup}; use --force only after verifying it is safe")

    used = get_path_size_bytes(src)
    min_extra = parse_size(args.xbuffermin)
    explicit_size = parse_size(args.size) if args.size else None
    size_bytes = calculate_tmpfs_size(used, args.xbuffer, min_extra, explicit_size)

    log(f"ramfscpy: source:        {src}", args)
    log(f"ramfscpy: source type:   {src_type}", args)
    log(f"ramfscpy: copy mode:     {copy_mode}", args)
    log(f"ramfscpy: source size:   {format_iec(used)}", args)
    log(f"ramfscpy: tmpfs size:    {format_iec(size_bytes)}", args)
    log(f"ramfscpy: mount point:   {mountpoint}", args)
    log(f"ramfscpy: RAM copy:      {dest}", args)
    if not args.no_bind:
        log(f"ramfscpy: backup path:   {backup}", args)
        log(f"ramfscpy: bind source:   {bind_src}", args)
        log(f"ramfscpy: bind target:   {src}", args)

    make_state_dir(args, dry_run=args.dry_run)

    mounted_here = False
    backup_created = False
    placeholder_created = False
    bind_done = False

    try:
        mounted_here = mount_tmpfs(mountpoint, size_bytes, dry_run=args.dry_run, args=args)
        check_destination_ready(dest, copy_mode, force=args.force)

        if copy_mode in {"contents", "self"}:
            ensure_dir_with_owner(dest, dry_run=args.dry_run, args=args)
        else:
            ensure_dir_with_owner(dest.parent, dry_run=args.dry_run, args=args)

        rsync_copy(src, dest, copy_mode=copy_mode, excludes=args.exclude, dry_run=args.dry_run, args=args)

        if not args.no_bind:
            if args.dry_run:
                log(f"+ mv {shlex.quote(str(src))} {shlex.quote(str(backup))}", args, dry_run=True)
                if src_type == "dir":
                    log(f"+ mkdir -p {shlex.quote(str(src))}", args, dry_run=True)
                else:
                    log(f"+ touch {shlex.quote(str(src))}", args, dry_run=True)
            else:
                src.rename(backup)
                backup_created = True
                if src_type == "dir":
                    src.mkdir(parents=False, exist_ok=False)
                else:
                    src.touch(exist_ok=False)
                placeholder_created = True

            run(["mount", "--bind", str(bind_src), str(src)], sudo=True, dry_run=args.dry_run, args=args)
            bind_done = True

        state = {
            "state_version": STATE_VERSION,
            "tool_version": VERSION,
            "created_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            "key": key,
            "raw_path": raw_path,
            "src": str(src),
            "src_type": src_type,
            "copy_mode": copy_mode,
            "mount": str(mountpoint),
            "dest": str(dest),
            "bind_src": str(bind_src),
            "backup": str(backup) if not args.no_bind else None,
            "bind": not args.no_bind,
            "mounted_here": mounted_here,
            "generated_mount": generated_mount,
            "writeback": bool(args.writeback),
            "exclude": list(args.exclude),
            "used_bytes_at_mount": used,
            "tmpfs_size_bytes": size_bytes,
        }
        write_json(sp, state, dry_run=args.dry_run, args=args)

    except Exception:
        log("ramfscpy: mount failed; attempting conservative rollback", args, force=True)
        if bind_done:
            try:
                run(["umount", str(src)], sudo=True, dry_run=args.dry_run, args=args)
            except Exception as exc:
                log(f"ramfscpy: rollback warning: failed to unmount bind target: {exc}", args, force=True)
        if placeholder_created:
            try:
                remove_placeholder(src, src_type, dry_run=False, args=args)
            except Exception as exc:
                log(f"ramfscpy: rollback warning: failed to remove placeholder path: {exc}", args, force=True)
        if backup_created:
            try:
                backup.rename(src)
            except Exception as exc:
                log(f"ramfscpy: rollback warning: failed to restore backup: {exc}", args, force=True)
        if mounted_here:
            try:
                run(["umount", str(mountpoint)], sudo=True, dry_run=args.dry_run, args=args)
            except Exception as exc:
                log(f"ramfscpy: rollback warning: failed to unmount tmpfs: {exc}", args, force=True)
        raise

    log("ramfscpy: mounted successfully", args)
    if args.writeback:
        log("ramfscpy: writeback is enabled; `unmount` will sync changes back", args)
    else:
        log("ramfscpy: writeback is disabled; use `ramfscpy sync <path>` or `unmount --sync` to keep changes", args)

    if not args.silent and not args.dry_run:
        print(str(mountpoint))


def sync_from_state(data: dict[str, Any], *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    dest = Path(data["dest"])
    src = Path(data["src"])
    src_type = data.get("src_type", "dir")
    copy_mode = data.get("copy_mode", "self" if src_type == "dir" else "file")
    bind = bool(data["bind"])
    backup_text = data.get("backup")
    excludes = list(data.get("exclude") or [])

    if bind:
        if not backup_text:
            die("state file says bind=true but backup path is missing")
        target = Path(backup_text)
    else:
        target = src

    if not dest.exists():
        die(f"RAM copy does not exist: {dest}")
    if not target.exists():
        die(f"sync target does not exist: {target}")

    log(f"ramfscpy: syncing {dest} -> {target}", args)
    rsync_sync(dest, target, copy_mode=copy_mode, excludes=excludes, dry_run=dry_run, args=args)


def cmd_sync(args: argparse.Namespace) -> None:
    _src, _sp, data = load_state_for_path(args.path)
    sync_from_state(data, dry_run=args.dry_run, args=args)
    log("ramfscpy: sync completed", args)


def remove_empty_generated_mountpoint(mountpoint: Path, *, dry_run: bool = False, args: argparse.Namespace | None = None) -> None:
    if dry_run:
        log(f"+ rmdir {shlex.quote(str(mountpoint))}", args, dry_run=True)
        return
    try:
        mountpoint.rmdir()
    except FileNotFoundError:
        pass
    except OSError:
        # Leave it behind if something else is there.
        pass


def cleanup_ram_copy_for_existing_mount(data: dict[str, Any], *, dry_run: bool, args: argparse.Namespace | None) -> None:
    dest = Path(data["dest"])
    copy_mode = data.get("copy_mode", "self")

    if copy_mode == "contents":
        # In contents mode, dest is the mount root. If this tool did not create
        # the tmpfs mount, deleting the root would be dangerous. Leave it alone.
        log("ramfscpy: leaving contents in existing mount root; not safe to delete mount root", args)
        return

    if dest.exists():
        remove_path(dest, dry_run=dry_run, args=args)


def cmd_unmount(args: argparse.Namespace) -> None:
    src, sp, data = load_state_for_path(args.path)

    bind = bool(data["bind"])
    mounted_here = bool(data["mounted_here"])
    generated_mount = bool(data.get("generated_mount"))
    mountpoint = Path(data["mount"])
    src_type = data.get("src_type", "dir")
    backup = Path(data["backup"]) if data.get("backup") else None
    should_sync = bool(args.sync or data.get("writeback"))

    if should_sync:
        sync_from_state(data, dry_run=args.dry_run, args=args)

    if bind:
        if backup is None:
            die("state file says bind=true but backup path is missing")

        log(f"ramfscpy: unmounting bind target: {src}", args)
        run(["umount", str(src)], sudo=True, dry_run=args.dry_run, args=args)

        if args.dry_run:
            remove_placeholder(src, src_type, dry_run=True, args=args)
            log(f"+ mv {shlex.quote(str(backup))} {shlex.quote(str(src))}", args, dry_run=True)
        else:
            remove_placeholder(src, src_type, dry_run=False, args=args)
            backup.rename(src)
    else:
        cleanup_ram_copy_for_existing_mount(data, dry_run=args.dry_run, args=args)

    if mounted_here:
        log(f"ramfscpy: unmounting tmpfs: {mountpoint}", args)
        run(["umount", str(mountpoint)], sudo=True, dry_run=args.dry_run, args=args)
        if generated_mount:
            remove_empty_generated_mountpoint(mountpoint, dry_run=args.dry_run, args=args)
    else:
        cleanup_ram_copy_for_existing_mount(data, dry_run=args.dry_run, args=args)

    if args.dry_run:
        log(f"+ rm {shlex.quote(str(sp))}", args, dry_run=True)
    else:
        try:
            sp.unlink()
        except FileNotFoundError:
            pass

    log("ramfscpy: unmounted successfully", args)


def print_state(data: dict[str, Any], sp: Path) -> None:
    src = Path(data["src"])
    mountpoint = Path(data["mount"])
    print(f"source:        {src}")
    print(f"state:         {sp}")
    print(f"created_at:    {data.get('created_at', '-')}")
    print(f"type:          {data.get('src_type', 'dir')}")
    print(f"copy mode:     {data.get('copy_mode', '-')}")
    print(f"mount:         {mountpoint}")
    print(f"RAM copy:      {data.get('dest', '-')}")
    print(f"bind source:   {data.get('bind_src', '-')}")
    print(f"bind:          {data.get('bind')}")
    print(f"mounted_here:  {data.get('mounted_here')}")
    print(f"generated:     {data.get('generated_mount', False)}")
    print(f"writeback:     {data.get('writeback')}")
    if data.get("backup"):
        print(f"backup:        {data['backup']}")
    if data.get("used_bytes_at_mount") is not None:
        print(f"source size:   {format_iec(int(data['used_bytes_at_mount']))}")
    if data.get("tmpfs_size_bytes") is not None:
        print(f"tmpfs size:    {format_iec(int(data['tmpfs_size_bytes']))}")
    print(f"src mounted:   {is_mountpoint(src)}")
    print(f"mount active:  {is_mountpoint(mountpoint)}")


def cmd_status(args: argparse.Namespace) -> None:
    if args.path:
        _src, sp, data = load_state_for_path(args.path)
        print_state(data, sp)
        return

    d = state_dir()
    if not d.exists():
        print("no ramfscpy states")
        return

    files = sorted(d.glob("*.json"))
    if not files:
        print("no ramfscpy states")
        return

    for i, sp in enumerate(files):
        if i:
            print()
        try:
            data = read_json(sp)
            print_state(data, sp)
        except SystemExit:
            print(f"state: {sp}")
            print("error: could not read state")


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--silent", action="store_true", help="print nothing on success; requires --mount for mount")
    group.add_argument("--verbose", action="store_true", help="print detailed progress to stderr")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ramfscpy",
        description="Copy a file or directory into tmpfs and optionally bind-mount it back onto the original path.",
    )
    parser.add_argument("--version", action="version", version=f"ramfscpy {VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_mount = sub.add_parser("mount", help="copy path into tmpfs and bind-mount it")
    add_output_flags(p_mount)
    p_mount.add_argument("path", help="file or directory to copy into RAM")
    p_mount.add_argument("--mount", default=None, help="tmpfs mount point; omitted means /run/mnt/<user>/ramfscpy/<random8>")
    p_mount.add_argument("--xbuffer", type=parse_nonnegative_float, default=DEFAULT_XBUFFER, help="extra size ratio; 0.1 means 10%%")
    p_mount.add_argument("--xbuffermin", default=DEFAULT_XBUFFER_MIN, help=f"minimum extra size; default: {DEFAULT_XBUFFER_MIN}")
    p_mount.add_argument("--size", help="explicit tmpfs size, e.g. 2G; overrides xbuffer calculation")
    p_mount.add_argument("--no-bind", action="store_true", help="only copy to tmpfs; do not bind-mount over original path")
    p_mount.add_argument("--writeback", action="store_true", help="make `unmount` sync changes back by default")
    p_mount.add_argument("--exclude", action="append", default=[], help="rsync exclude pattern for directories; may be repeated")
    p_mount.add_argument("--force", action="store_true", help="allow reuse of existing state/dest/backup paths after manual verification")
    p_mount.add_argument("--dry-run", action="store_true", help="print actions without making changes")
    p_mount.set_defaults(func=cmd_mount)

    p_sync = sub.add_parser("sync", help="copy RAM-side changes back to original backup/source")
    add_output_flags(p_sync)
    p_sync.add_argument("path", help="original source file or directory path")
    p_sync.add_argument("--dry-run", action="store_true", help="print actions without making changes")
    p_sync.set_defaults(func=cmd_sync)

    p_unmount = sub.add_parser("unmount", help="undo bind mount and tmpfs mount")
    add_output_flags(p_unmount)
    p_unmount.add_argument("path", help="original source file or directory path")
    p_unmount.add_argument("--sync", action="store_true", help="sync changes back before unmounting")
    p_unmount.add_argument("--dry-run", action="store_true", help="print actions without making changes")
    p_unmount.set_defaults(func=cmd_unmount)

    p_status = sub.add_parser("status", help="show active ramfscpy state")
    p_status.add_argument("path", nargs="?", help="original source file or directory path; omitted lists all states")
    p_status.set_defaults(func=cmd_status)

    return parser


def normalize_legacy_argv(argv: list[str]) -> list[str]:
    """
    Support shorthand:
      ramfscpy --xbuffer=0.1 --xbuffermin=64M myapp/
    as:
      ramfscpy mount --xbuffer=0.1 --xbuffermin=64M myapp/
    """
    if not argv:
        return argv
    commands = {"mount", "sync", "unmount", "status"}
    if argv[0] in {"-h", "--help", "--version"}:
        return argv
    if argv[0] in commands:
        return argv
    return ["mount", *argv]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = normalize_legacy_argv(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        args.func(args)
        return 0
    except RamfsCpyError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        eprint("ramfscpy: interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

