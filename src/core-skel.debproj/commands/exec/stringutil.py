#!/usr/bin/env python3

# Usage
"""

stringutil <operation> then <postwork>

operations:
- replace
- lowercase
- uppercase
- capitalize
- camelcase

postwork:
- print
- assign

Usage example:
stringutil replace " " with "space" in "Hello World" then print
stringutil lowercase "Hello World" then print
stringutil uppercase "Hello World" then assign MY_VAR
"""

import sys


def usage():
    print("Usage:")
    print('  stringutil replace "old" with "new" in "text" then print')
    print('  stringutil lowercase "text" then print')
    print('  stringutil uppercase "text" then print')
    print('  stringutil capitalize "text" then print')
    print('  stringutil title "text" then print')
    print('  stringutil camelcase "text" then print')
    print('  stringutil lowercase "text" then assign MY_VAR')


def find_then(args):
    if "then" not in args:
        raise ValueError("Missing 'then'")

    return args.index("then")


def run_operation(args):
    if not args:
        raise ValueError("Missing operation")

    operation = args[0]

    if operation == "replace":
        return replace_op(args)

    if operation == "lowercase":
        return lowercase_op(args)

    if operation == "uppercase":
        return uppercase_op(args)

    if operation == "capitalize":
        return capitalize_op(args)

    if operation == "title":
        return title_op(args)

    if operation == "camelcase":
        return camelcase_op(args)

    raise ValueError(f"Unknown operation: {operation}")


def replace_op(args):
    # replace OLD with NEW in TEXT
    if len(args) != 6:
        raise ValueError('Usage: replace "old" with "new" in "text"')

    if args[2] != "with":
        raise ValueError("Missing 'with'")

    if args[4] != "in":
        raise ValueError("Missing 'in'")

    old = args[1]
    new = args[3]
    text = args[5]

    return text.replace(old, new)


def lowercase_op(args):
    if len(args) != 2:
        raise ValueError('Usage: lowercase "text"')

    return args[1].lower()


def uppercase_op(args):
    if len(args) != 2:
        raise ValueError('Usage: uppercase "text"')

    return args[1].upper()


def capitalize_op(args):
    if len(args) != 2:
        raise ValueError('Usage: capitalize "text"')

    return args[1].capitalize()


def title_op(args):
    if len(args) != 2:
        raise ValueError('Usage: title "text"')

    return args[1].title()


def camelcase_op(args):
    if len(args) != 2:
        raise ValueError('Usage: camelcase "text"')

    words = args[1].split()

    if not words:
        return ""

    first = words[0].lower()
    rest = ""

    for word in words[1:]:
        rest += word[:1].upper() + word[1:].lower()

    return first + rest


def handle_postwork(result, args):
    if not args:
        raise ValueError("Missing postwork")

    postwork = args[0]

    if postwork == "print":
        if len(args) != 1:
            raise ValueError("Usage: then print")

        print(result)
        return

    if postwork == "assign":
        if len(args) != 2:
            raise ValueError("Usage: then assign VAR_NAME")

        var_name = args[1]
        print(f'{var_name}="{result}"')
        return

    raise ValueError(f"Unknown postwork: {postwork}")


def main():
    args = sys.argv[1:]

    try:
        then_index = find_then(args)

        operation_args = args[:then_index]
        postwork_args = args[then_index + 1:]

        result = run_operation(operation_args)
        handle_postwork(result, postwork_args)

    except ValueError as e:
        print(f"Error: {e}")
        usage()
        sys.exit(1)


if __name__ == "__main__":
    main()