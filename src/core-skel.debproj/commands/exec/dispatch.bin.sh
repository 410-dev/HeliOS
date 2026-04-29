#!/bin/bash

dispatch_exec() {
    local interactive=0
    local no_autoclose=0
    local open_query=""
    local order_select=""
    local print_name=0
    local print_pid=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -i|--interactive)
                interactive=1
                shift
                ;;
            --no-autoclose)
                no_autoclose=1
                shift
                ;;
            --open)
                open_query="$2"
                shift 2
                ;;
            --order-select)
                order_select="$2"
                shift 2
                ;;
            --name)
                print_name=1
                shift
                ;;
            --pid)
                print_pid=1
                shift
                ;;
            --)
                shift
                break
                ;;
            -*)
                echo "Unknown option: $1" >&2
                return 1
                ;;
            *)
                break
                ;;
        esac
    done

    _dispatch_attach() {
        local target="$1"

        if [[ -n "$TMUX" ]]; then
            tmux switch-client -t "$target"
        else
            tmux attach -t "$target"
        fi
    }

    _dispatch_open() {
        local query="$1"
        local selected=""

        local sessions
        sessions="$(
            tmux list-sessions -F '#{session_name}' 2>/dev/null \
                | grep -E "^${query}_[0-9]{8}_[0-9]{6}$|${query}" \
                | sort -r
        )"

        if [[ -n "$order_select" ]]; then
            local order="${order_select%%,*}"
            local index="${order_select##*,}"

            case "$order" in
                latest)
                    selected="$(printf '%s\n' "$sessions" | sed -n "$((index + 1))p")"
                    ;;
                oldest)
                    selected="$(printf '%s\n' "$sessions" | sort | sed -n "$((index + 1))p")"
                    ;;
                *)
                    echo "Unknown order: $order" >&2
                    return 1
                    ;;
            esac
        elif [[ "$(printf '%s\n' "$sessions" | sed '/^$/d' | wc -l)" -eq 1 ]]; then
            selected="$sessions"
        elif command -v fzf >/dev/null 2>&1; then
            selected="$(printf '%s\n' "$sessions" | fzf --prompt='dispatch> ')"
        else
            echo "Select session:"
            select selected in $sessions; do
                [[ -n "$selected" ]] && break
            done
        fi

        if [[ -z "$selected" ]]; then
            echo "No matching tmux session found for: $query" >&2
            return 1
        fi

        _dispatch_attach "$selected"
    }

    if [[ -n "$open_query" ]]; then
        _dispatch_open "$open_query"
        return $?
    fi

    if [[ $# -eq 0 ]]; then
        echo "Usage:"
        echo "    dispatch [--interactive|-i] [--no-autoclose] [--name] [--pid] <command> [args...]"
        echo "    dispatch --open <name> [--order-select latest,0]"
        return 1
    fi

    local bin
    bin="$(basename "$1")"

    local ts
    ts="$(date +%Y%m%d_%H%M%S)"

    local name="${bin}_${ts}"

    local cmd
    printf -v cmd '%q ' "$@"

    local wrapped
    if [[ "$no_autoclose" -eq 1 ]]; then
        wrapped="echo '+ $cmd'; $cmd; status=\$?; echo; echo '[exit:' \$status']'; exec \$SHELL"
    else
        wrapped="$cmd"
    fi

    if [[ "$interactive" -eq 1 ]]; then
        tmux new-session -s "$name" "$wrapped"
    else
        tmux new-session -d -s "$name" "$wrapped"

        if [[ "$print_name" -eq 1 ]]; then
            echo "$name"
        else
            echo "Started tmux session: $name"
            echo "Attach with: tmux attach -t $name"
        fi

        if [[ "$print_pid" -eq 1 ]]; then
            tmux display-message -p -t "$name" '#{pane_pid}'
        fi
    fi
}

dispatch_exec "$@"
