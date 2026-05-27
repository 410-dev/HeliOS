#!/usr/bin/env python3
# Usage: foreach [--ignore-error] [--no-verbose] <slicer> <stringified array> :: <command>

import sys
import subprocess
import shlex

USAGE = "Usage: foreach [--ignore-error] [--no-verbose] <slicer> <array> :: <command>"

def main() -> int:
    args = sys.argv[1:]

    # Locate :: separator first
    try:
        sep = args.index("::")
    except ValueError:
        print(f"Error: '::' separator not found\n{USAGE}", file=sys.stderr)
        return 2

    pre  = args[:sep]
    post = args[sep + 1:]

    # Parse flags
    ignore_error = "--ignore-error" in pre
    no_verbose   = "--no-verbose"   in pre
    positional   = [a for a in pre if not a.startswith("--")]

    if len(positional) < 2:
        print(f"Error: slicer and array are required\n{USAGE}", file=sys.stderr)
        return 2
    if not post:
        print(f"Error: command is required after '::'\n{USAGE}", file=sys.stderr)
        return 2

    slicer, array = positional[0], positional[1]
    elements = array.split(slicer)
    last_nonzero = 0

    for i, element in enumerate(elements):
        cmd = [arg.replace("{index}", str(i)).replace("{element}", element)
               for arg in post]

        if not no_verbose:
            print(f"[ForEach:{i}/{len(elements)-1}] {element}: {shlex.join(cmd)}", file=sys.stderr)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            print(line, end="")
        proc.wait()

        if proc.returncode != 0:
            last_nonzero = proc.returncode
            print(
                f"[ForEach:{i}/{len(elements)-1}] Failed (exit {proc.returncode}): {shlex.join(cmd)}",
                file=sys.stderr,
            )
            if not ignore_error:
                return last_nonzero  # 즉시 종료

    return last_nonzero

if __name__ == "__main__":
    sys.exit(main())
