#!/usr/bin/env python3

import json
import sys
import os

def compile_autocomplete(json_filepath, output_filepath):
    with open(json_filepath, 'r') as f:
        rules = json.load(f)

    command_name = ""
    param_mapping = {}

    # Identify the base command and map parameter names to their bash COMP_WORDS index
    for rule in rules:
        idx = rule.get("index")
        if idx == -1:
            command_name = rule.get("command")
        else:
            param_name = rule.get("param_name")
            if param_name:
                # COMP_WORDS[0] is the command, so index 0 is COMP_WORDS[1]
                if isinstance(idx, int):
                    param_mapping[param_name] = idx + 1
                elif isinstance(idx, list) and len(idx) > 0:
                    param_mapping[param_name] = idx[0] + 1

    if not command_name:
        raise ValueError("Error: Command name (index -1) not found in JSON.")

    # Start constructing the bash completion script
    bash_script = [
        f"_{command_name}_completions()",
        "{",
        "    local cur prev",
        '    cur="${COMP_WORDS[COMP_CWORD]}"',
        '    prev="${COMP_WORDS[COMP_CWORD-1]}"',
        '    COMP_WORDBREAKS="${COMP_WORDBREAKS//:}"',
        "    local idx=$((COMP_CWORD - 1))",
        ""
    ]

    # Extract named parameters into local variables for prerequisite evaluation
    for param, word_idx in param_mapping.items():
        safe_param = param.replace(" ", "_").replace("-", "_")
        bash_script.append(f'    local {safe_param}="${{COMP_WORDS[{word_idx}]:-}}"')

    bash_script.append("\n    case $idx in")

    # Group rules by index since multiple rules can share the same target index (e.g., conditional flags)
    index_rules = {}
    for rule in rules:
        idx = rule.get("index")
        if idx == -1:
            continue

        idx_tuple = tuple(idx) if isinstance(idx, list) else (idx,)
        if idx_tuple not in index_rules:
            index_rules[idx_tuple] = []
        index_rules[idx_tuple].append(rule)

    for idx_tuple, rules_for_idx in index_rules.items():
        idx_str = "|".join(map(str, idx_tuple))
        bash_script.append(f"        {idx_str})")

        has_prereqs = any(r.get("prerequisite") for r in rules_for_idx)

        for i, rule in enumerate(rules_for_idx):
            prereqs = rule.get("prerequisite", {})
            indent = "            "

            if prereqs:
                conditions = []
                for p_name, p_cond in prereqs.items():
                    safe_p_name = p_name.replace(" ", "_").replace("-", "_")
                    if "any_of" in p_cond:
                        or_conds = [f'"${safe_p_name}" == "{val}"' for val in p_cond["any_of"]]
                        conditions.append("(" + " || ".join(or_conds) + ")")

                if conditions:
                    if_stmt = "elif" if i > 0 else "if"
                    condition_str = " && ".join(conditions)
                    # Note: Bash string comparison requires using the variable, e.g., "$Action"
                    # condition_str = condition_str.replace('" == ', ' == ').replace('("', '(${')

                    bash_script.append(f"            {if_stmt} [[ {condition_str} ]]; then")
                    indent = "                "
            elif has_prereqs and i > 0:
                bash_script.append("            else")
                indent = "                "

            # Generate the action (static or dynamic list)
            action = rule.get("action")
            avail = rule.get("available", [])

            if action == "static-list":
                words = " ".join(avail)
                bash_script.append(f'{indent}COMPREPLY=( $(compgen -W "{words}" -- "$cur") )')
            elif action == "dynamic-list":
                cmd = " ".join(avail)
                bash_script.append(f'{indent}local dyn_opts=$({cmd})')
                bash_script.append(f'{indent}COMPREPLY=( $(compgen -W "$dyn_opts" -- "$cur") )')

        if has_prereqs:
            bash_script.append("            fi")

        bash_script.append("            ;;")

    bash_script.extend([
        "    esac",
        "    return 0",
        "}",
        "",
        f"complete -F _{command_name}_completions {command_name}\n"
    ])

    # Write the compiled script to the specified file
    with open(output_filepath, 'w') as f:
        f.write("\n".join(bash_script))

if __name__ == "__main__":

    # Require sudo
    if os.geteuid() != 0:
        print("This script must be run as root (sudo).")
        sys.exit(1)

    # Iterate json files in {{commands/autocompletes}}
    for filename in os.listdir("{{commands/autocompletes}}"):
        if filename.endswith(".json"):
            if "-v" in sys.argv:
                print(f"Compiling {filename}....", end='')
            json_path = os.path.join("{{commands/autocompletes}}", filename)
            output_path = os.path.join("/etc/bash_completion.d/", filename.replace(".json", ""))
            compile_autocomplete(json_path, output_path)
            if "-v" in sys.argv:
                print("OK")
