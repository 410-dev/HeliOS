#!/usr/bin/env python3
# Usage: foreach [--ignore-error] [--no-verbose] [--slicer=SEP] <elements...> :: <command>

import sys
import subprocess
import shlex

USAGE = "Usage: foreach [--ignore-error] [--no-verbose] [--slicer=SEP] <elements...> :: <command>"

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

    if not post:
        print(f"Error: command is required after '::'\n{USAGE}", file=sys.stderr)
        return 2

    # Parse flags
    ignore_error = "--ignore-error" in pre
    no_verbose   = "--no-verbose"   in pre

    slicer = None
    for a in pre:
        if a.startswith("--slicer="):
            slicer = a[len("--slicer="):]
            break

    positional = [a for a in pre if not a.startswith("--")]

    # Build elements list
    if slicer is not None:
        # --slicer 지정 시: positional은 정확히 하나의 문자열이어야 함
        if len(positional) != 1:
            print(
                f"Error: exactly one array argument required when --slicer is used\n{USAGE}",
                file=sys.stderr,
            )
            return 2
        elements = positional[0].split(slicer)
    else:
        # 기본: 여러 인자를 받거나, 단일 문자열을 공백/라인브레이크로 분리
        if len(positional) == 1:
            elements = positional[0].split()  # split()은 공백+라인브레이크 모두 처리
        else:
            elements = positional  # 여러 인자를 그대로 사용

    if not elements:
        print(f"Error: no elements to iterate over\n{USAGE}", file=sys.stderr)
        return 2

    last_nonzero = 0

    for i, element in enumerate(elements):
        cmd = [arg.replace("{index}", str(i)).replace("{item}", element)
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
                return last_nonzero

    return last_nonzero

if __name__ == "__main__":
    sys.exit(main())
