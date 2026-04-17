#!/usr/bin/env python3
# HeliOS build tool — usage: build -v <edition>

import argparse
import copy
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


# ── JSON5 parsing ──────────────────────────────────────────────────────────────

def _strip_json5_comments(text):
    """String-aware comment stripper: handles // and /* */ without clobbering URLs in strings."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\":
                    i += 1
                    if i < n:
                        out.append(text[i])
                elif c == '"':
                    break
                i += 1
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_json5(text):
    """Strip JSON5 comments and trailing commas, then parse as JSON.
    Iteratively removes offending lines to tolerate incomplete/orphan entries."""
    text = _strip_json5_comments(text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    for _ in range(20):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            lines = text.splitlines()
            # "Expecting ':'" means a key on the previous line is missing its value
            if "Expecting ':'" in str(exc):
                idx = exc.lineno - 2  # The orphan key is one line above the error
                while idx > 0 and not lines[idx].strip():
                    idx -= 1
            else:
                idx = exc.lineno - 1
            if 0 <= idx < len(lines):
                lines.pop(idx)
                text = "\n".join(lines)
                text = re.sub(r",\s*([}\]])", r"\1", text)
            else:
                raise
    return json.loads(text)


def load_json5(path):
    with open(path, "r", encoding="utf-8") as f:
        return parse_json5(f.read())


def to_debian_dep(dep):
    """Convert 'pkg>=1.0' / 'pkg=1.0' style deps to Debian 'pkg (>= 1.0)' format."""
    for op in (">=", "<=", ">>", "<<", "="):
        if op in dep:
            pkg, ver = dep.split(op, 1)
            return f"{pkg.strip()} ({op} {ver.strip()})"
    return dep


# ── Recipe merging ─────────────────────────────────────────────────────────────

def deep_merge(base, override):
    """Merge override on top of base; override wins, base fills missing keys."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


# ── Text substitution ──────────────────────────────────────────────────────────

def apply_subs(text, subs):
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def is_binary(path):
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def substitute_tree(root, subs, skip_dirs=None):
    """Apply text substitutions to all non-binary files under root."""
    skip_dirs = skip_dirs or set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if is_binary(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                new_content = apply_subs(content, subs)
                if new_content != content:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new_content)
            except OSError:
                pass


# ── File utilities ─────────────────────────────────────────────────────────────

def make_executable(path):
    s = os.stat(path)
    os.chmod(path, s.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_dir_contents(src, dest):
    """Recursively copy src into dest, skipping nested .debproj/.apprunxproj dirs."""
    for item in os.listdir(src):
        isrc = os.path.join(src, item)
        idst = os.path.join(dest, item)
        if os.path.isdir(isrc):
            if item.endswith(".debproj") or item.endswith(".apprunxproj"):
                continue  # Nested project dirs are built separately
            os.makedirs(idst, exist_ok=True)
            copy_dir_contents(isrc, idst)
        else:
            shutil.copy2(isrc, idst)


def process_executable_files(root):
    """Rename .bin.sh → executable, and .py with #!/usr/bin/python3 shebang → executable."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "DEBIAN"]
        for fname in list(filenames):
            fpath = os.path.join(dirpath, fname)
            if fname.endswith(".bin.sh"):
                new_path = os.path.join(dirpath, fname[: -len(".bin.sh")])
                os.rename(fpath, new_path)
                make_executable(new_path)
            elif fname.endswith(".py"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        first_line = f.readline()
                    if first_line.startswith("#!/usr/bin/python3"):
                        new_path = os.path.join(dirpath, fname[: -len(".py")])
                        os.rename(fpath, new_path)
                        make_executable(new_path)
                except OSError:
                    pass


# ── Debproj builder ────────────────────────────────────────────────────────────

def build_debproj(debproj_dir, output_dir, recipe, verbose):
    """Build a .debproj directory into a .deb file. Returns output path or None."""
    subs = recipe.get("TextSubstitute", {})
    deb_name_tpl = recipe.get("DebianPackageName", "{{name}}-{{version}}.deb")

    info_dir = os.path.join(debproj_dir, "_INFO")
    pkg_path = os.path.join(info_dir, "package.json5")
    mapping_path = os.path.join(info_dir, "mapping.json5")

    if not os.path.exists(pkg_path):
        print(f"  [WARN] No _INFO/package.json5 in {debproj_dir}, skipping.")
        return None

    pkg = load_json5(pkg_path)

    name = apply_subs(pkg.get("name", "unknown"), subs)
    version = apply_subs(pkg.get("version", "0"), subs)
    arch = apply_subs(pkg.get("architecture", "all"), subs)
    maintainer = apply_subs(
        pkg.get("maintainer", "HeliOS Team <noreply@example.com>"), subs
    )
    description = apply_subs(pkg.get("description", name), subs)

    def resolve_list(field):
        return [to_debian_dep(apply_subs(x, subs)) for x in pkg.get(field, [])]

    depends = resolve_list("depends")
    conflicts = resolve_list("conflicts")
    provides = resolve_list("provides")
    replaces = resolve_list("replaces")

    name_subs = dict(subs)
    name_subs.update({"name": name, "version": version, "architecture": arch})
    deb_filename = apply_subs(deb_name_tpl, name_subs)

    print(f"  Building {os.path.basename(debproj_dir)}: {name} {version} → {deb_filename}")

    with tempfile.TemporaryDirectory() as tmpdir:
        debian_dir = os.path.join(tmpdir, "DEBIAN")
        os.makedirs(debian_dir)

        # Apply file mapping
        if os.path.exists(mapping_path):
            try:
                mapping = load_json5(mapping_path)
            except Exception as exc:
                print(f"  [WARN] Could not parse mapping.json5: {exc}")
                mapping = {}

            for src_subdir, dest_path in mapping.items():
                if not isinstance(dest_path, str):
                    if verbose:
                        print(f"    [WARN] Skipping invalid mapping entry: {src_subdir!r}")
                    continue
                src = os.path.join(debproj_dir, src_subdir)
                if not os.path.exists(src):
                    if verbose:
                        print(f"    [WARN] Mapping source not found: {src}")
                    continue
                dest = tmpdir + dest_path  # dest_path is absolute e.g. /usr/bin
                os.makedirs(dest, exist_ok=True)
                copy_dir_contents(src, dest)

        process_executable_files(tmpdir)

        # Write DEBIAN/control
        control = [
            f"Package: {name}",
            f"Version: {version}",
            f"Architecture: {arch}",
            f"Maintainer: {maintainer}",
        ]
        if depends:
            control.append(f"Depends: {', '.join(depends)}")
        if conflicts:
            control.append(f"Conflicts: {', '.join(conflicts)}")
        if provides:
            control.append(f"Provides: {', '.join(provides)}")
        if replaces:
            control.append(f"Replaces: {', '.join(replaces)}")
        control.append(f"Description: {description}")
        control.append("")

        with open(os.path.join(debian_dir, "control"), "w") as f:
            f.write("\n".join(control))

        # Merge maintainer scripts from *.d directories
        for script_name in ("preinst", "postinst", "prerm", "postrm"):
            scripts_dir = os.path.join(info_dir, f"{script_name}.d")
            if not os.path.isdir(scripts_dir):
                continue
            parts = ["#!/bin/bash", "set -e", ""]
            for sf in sorted(os.listdir(scripts_dir)):
                sfp = os.path.join(scripts_dir, sf)
                if not os.path.isfile(sfp):
                    continue
                with open(sfp, "r", encoding="utf-8") as f:
                    content = f.read()
                # Strip shebang to avoid duplicates when combining
                if content.startswith("#!"):
                    content = content[content.find("\n") + 1 :]
                parts.append(content)
            script_out = os.path.join(debian_dir, script_name)
            with open(script_out, "w", encoding="utf-8") as f:
                f.write("\n".join(parts))
            os.chmod(script_out, 0o755)

        # Build the .deb
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, deb_filename)
        result = subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", tmpdir, out_path],
            capture_output=not verbose,
            text=True,
        )
        if result.returncode != 0:
            if not verbose and result.stderr:
                print(result.stderr, file=sys.stderr)
            print(f"  [ERROR] dpkg-deb failed for {name}", file=sys.stderr)
            return None

        print(f"  Built: {out_path}")
        return out_path


# ── AppRunX builder ────────────────────────────────────────────────────────────

def build_apprunxproj(proj_dir, output_dir, recipe, verbose):
    """Package a .apprunxproj directory into a .apprunx archive (zip)."""
    proj_stem = os.path.basename(proj_dir)
    if proj_stem.endswith(".apprunxproj"):
        proj_stem = proj_stem[: -len(".apprunxproj")]

    subs = dict(recipe.get("TextSubstitute", {}))
    subs["filename"] = proj_stem
    pkg_name = apply_subs(recipe.get("AppRunPackageName", "{{filename}}.apprunx"), subs)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, pkg_name)

    print(f"  Packaging {os.path.basename(proj_dir)} → {pkg_name}")
    zip_base = out_path[: -len(".apprunx")] if out_path.endswith(".apprunx") else out_path
    shutil.make_archive(zip_base, "zip", proj_dir)
    zip_path = zip_base + ".zip"
    if os.path.exists(zip_path):
        os.rename(zip_path, out_path)

    print(f"  Built: {out_path}")
    return out_path


# ── Project discovery ──────────────────────────────────────────────────────────

def find_project_dirs(workspace):
    """Find all .debproj and .apprunxproj directories under workspace (excluding _deps)."""
    results = []

    def _walk(path):
        try:
            entries = list(os.scandir(path))
        except PermissionError:
            return
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name == "_deps":
                continue
            if entry.name.endswith(".debproj") or entry.name.endswith(".apprunxproj"):
                results.append(entry.path)
                _walk(entry.path)  # Recurse to find nested project dirs
            else:
                _walk(entry.path)

    _walk(workspace)
    return results


# ── Main build orchestrator ────────────────────────────────────────────────────

def run_build(edition, verbose):
    # Locate project root: this script is at <root>/.build/tools/build.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))

    print(f"Project root : {project_root}")
    print(f"Edition      : {edition}")

    common_path = os.path.join(project_root, ".build", "common.json5")
    recipe_path = os.path.join(project_root, ".build", f"{edition}.json5")

    if not os.path.exists(common_path):
        sys.exit(f"[ERROR] common.json5 not found: {common_path}")
    if not os.path.exists(recipe_path):
        sys.exit(f"[ERROR] Recipe not found: {recipe_path}")

    common = load_json5(common_path)
    edition_data = load_json5(recipe_path)
    recipe = deep_merge(common, edition_data)

    subs = recipe.get("TextSubstitute", {})
    builds = recipe.get("Build", [])
    dep_builds = recipe.get("DependencyBuilds", [])

    print(f"Substitutions: {subs}")
    print(f"Build targets : {builds}")
    print(f"Dependencies  : {dep_builds}")

    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="helios-build-") as workspace:
        # ── Steps 5-7: Copy .debproj sources into workspace ────────────────────
        print("\n[1/5] Copying build targets to workspace...")
        for build_name in builds:
            src = os.path.join(project_root, "src", f"{build_name}.debproj")
            dst = os.path.join(workspace, f"{build_name}.debproj")
            if not os.path.exists(src):
                print(f"  [WARN] Source not found: {src}  (skipping)")
                continue
            shutil.copytree(src, dst)
            print(f"  Copied {build_name}.debproj")

        # ── Steps 8-12: Build external dependencies ────────────────────────────
        if dep_builds:
            print("\n[2/5] Building dependencies...")
            dep_workspace = os.path.join(workspace, "_deps")
            os.makedirs(dep_workspace)

            for dep_name in dep_builds:
                dep_spec = os.path.join(
                    project_root, "dependencies", f"{dep_name}.json5"
                )
                if not os.path.exists(dep_spec):
                    print(f"  [WARN] Dependency spec not found: {dep_spec}  (skipping)")
                    continue

                dep_info = load_json5(dep_spec)
                repo = dep_info.get("repo")
                branch = dep_info.get("branch", "main")
                clone_name = dep_info.get("name", dep_name)
                clone_dir = os.path.join(dep_workspace, clone_name)

                print(f"  Cloning {clone_name} ({repo}, branch={branch})...")
                result = subprocess.run(
                    ["git", "clone", repo, "--branch", branch, "--depth", "1", clone_dir],
                    capture_output=not verbose,
                    text=True,
                )
                if result.returncode != 0:
                    if not verbose and result.stderr:
                        print(result.stderr, file=sys.stderr)
                    print(f"  [WARN] git clone failed for {clone_name}, skipping.")
                    continue

                build_sh = os.path.join(clone_dir, "build.sh")
                if os.path.exists(build_sh):
                    print(f"  Running build.sh for {clone_name}...")
                    res = subprocess.run(
                        ["bash", "build.sh"],
                        cwd=clone_dir,
                        capture_output=not verbose,
                        text=True,
                    )
                    if res.returncode != 0:
                        if not verbose and res.stderr:
                            print(res.stderr, file=sys.stderr)
                        print(f"  [WARN] build.sh failed for {clone_name}.")
                else:
                    apprunx_files = list(Path(clone_dir).rglob("*.apprunx"))
                    debproj_dirs = list(Path(clone_dir).rglob("*.debproj"))
                    if apprunx_files:
                        for af in apprunx_files:
                            print(f"  Copying {af.name} to deps...")
                            shutil.copy2(str(af), dep_workspace)
                    elif debproj_dirs:
                        for dp in debproj_dirs:
                            build_debproj(str(dp), dep_workspace, recipe, verbose)
                    else:
                        print(
                            f"  [WARN] No build.sh, .apprunx, or .debproj in {clone_name}."
                        )
        else:
            print("\n[2/5] No dependencies to build.")

        # ── Steps 13-14: Text substitution ────────────────────────────────────
        print("\n[3/5] Applying text substitutions...")
        substitute_tree(workspace, subs, skip_dirs={"_deps"})
        print("  Done.")

        # ── Step 15: Build all packages, deepest first ────────────────────────
        print("\n[4/5] Building packages...")
        proj_dirs = find_project_dirs(workspace)
        proj_dirs.sort(key=lambda p: p.count(os.sep), reverse=True)

        if verbose:
            print("  Build order:")
            for pd in proj_dirs:
                print(f"    {pd}")

        built_files = []
        for proj_dir in proj_dirs:
            parent_dir = os.path.dirname(proj_dir)
            if proj_dir.endswith(".debproj"):
                out = build_debproj(proj_dir, parent_dir, recipe, verbose)
                if out:
                    built_files.append(out)
            elif proj_dir.endswith(".apprunxproj"):
                # Build in-place so the .apprunx sits alongside the .apprunxproj dir
                # and gets picked up by the parent .debproj's file mapping.
                # Do NOT add to built_files — it is not a standalone output package.
                build_apprunxproj(proj_dir, parent_dir, recipe, verbose)

        # Collect any packages produced by dependency builds
        dep_workspace = os.path.join(workspace, "_deps")
        if os.path.exists(dep_workspace):
            for ext in ("*.deb", "*.apprunx"):
                for f in Path(dep_workspace).rglob(ext):
                    built_files.append(str(f))

        # ── Step 16: Copy all built packages to output/ ───────────────────────
        print("\n[5/5] Copying to output...")
        if not built_files:
            print("  No packages were built.")
        for bf in built_files:
            dst = os.path.join(output_dir, os.path.basename(bf))
            shutil.copy2(bf, dst)
            print(f"  {os.path.basename(bf)}")

        print(f"\nDone! {len(built_files)} package(s) written to {output_dir}/")


def main():
    parser = argparse.ArgumentParser(
        prog="build",
        description="Build HeliOS packages from a recipe.",
    )
    parser.add_argument(
        "-v",
        dest="edition",
        required=True,
        metavar="EDITION",
        help="Edition to build (e.g. enterprise, common)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output including subprocess output",
    )
    args = parser.parse_args()
    run_build(args.edition, args.verbose)


if __name__ == "__main__":
    main()
