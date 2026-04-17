#!/bin/bash

# Expected usage:
# ./services.sh enable <id>
# ./services.sh disable <id>
# ./services.sh restart <id>  # same as disable + enable
# ./services.sh status <id>
# ./services.sh logs <id>
# ./services.sh journal <id>  # same as logs but journalctl -xeu
# ./services.sh name <id> 
# ./services.sh list

ACTION=$1
SERVICE_ID=$2

# Optional flag to control behavior when multiple matching instances are found.
# Supported values: terminate, first, last
MULTI_ACTION="interactive"

# Handle optional parameter --multiple-instances-action=...
for arg in "$@"; do
    case $arg in
        --multiple-instances-action=*)
            MULTI_ACTION="${arg#*=}"
            ;;
    esac
done

# Print usage if arguments are not provided correctly
case $ACTION in
    enable|restart|status|logs|journal|disable|name|list) ;;
    * )
        echo "Usage: $0 {enable|restart|status|logs|journal|disable|name|list} <service_id | (for list, no service_id needed)> [--multiple-instances-action=terminate|first|last]"
        echo "When multiple bundles match a service_id, the optional flag controls behavior:" \
             "terminate -> abort; first -> pick alphabetically first; last -> pick alphabetically last; omit -> interactive selection."
        echo "Examples:"
        echo "  $0 enable myservice"
        echo "  $0 status myservice --multiple-instances-action=first"
        exit 1
        ;;
esac

# Services location
# Priority order:
#  1. {{SYS_SERVICES}}/<service_id>.apprun
#  2. {{OPT_SERVICES}}/<service_id>.apprun

RAW_DIRECTORIES=("{{SYS_SERVICES}}" "{{OPT_SERVICES}}")
DIRECTORIES=($(printf "%s\n" "${RAW_DIRECTORIES[@]}" | sort -u))
if [ "$ACTION" == "list" ]; then
    for DIR in "${DIRECTORIES[@]}"; do
        if [ -d "$DIR" ]; then
            find "$DIR" -maxdepth 1 -type d -name "*.apprun" | while read -r SERVICE_DIR; do
                SERVICE_BASENAME=$(basename "$SERVICE_DIR" .apprun)
                echo "$SERVICE_BASENAME"
            done
        fi
    done
    exit 0
fi

# Search for the service with ending <service_id>.apprun
# For example, if input is "abcd" and has bundles like "xyz.abcd.apprun" or "zzz.abcd.apprun",
# collect all matches across DIRECTORIES.
MATCHES=()
for DIR in "${DIRECTORIES[@]}"; do
    if [ -d "$DIR" ]; then
        while IFS= read -r m; do
            [ -n "$m" ] && MATCHES+=("$m")
        done < <(find "$DIR" -maxdepth 1 -type d -name "*$SERVICE_ID.apprun" 2>/dev/null)
    fi
done

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "Service with ID '$SERVICE_ID' not found."
    exit 1
fi

# If exactly one match, use it. If multiple, handle according to MULTI_ACTION.
if [ ${#MATCHES[@]} -eq 1 ]; then
    SERVICE_PATH="${MATCHES[0]}"
else
    # Sort alphabetically by basename (directory name)
    IFS=$'\n' SORTED_MATCHES=($(for p in "${MATCHES[@]}"; do basename "$p"; done | sort))
    # Reconstruct full paths in sorted order
    SORTED_FULL=()
    for b in "${SORTED_MATCHES[@]}"; do
        for p in "${MATCHES[@]}"; do
            if [ "$(basename "$p")" = "$b" ]; then
                SORTED_FULL+=("$p")
                break
            fi
        done
    done

    case "$MULTI_ACTION" in
        terminate)
            echo "Multiple service bundles found for ID '$SERVICE_ID':"
            for p in "${SORTED_FULL[@]}"; do
                echo " - $(basename "$p") -> $p"
            done
            echo "Aborting due to --multiple-instances-action=terminate"
            exit 2
            ;;
        first)
            SERVICE_PATH="${SORTED_FULL[0]}"
            ;;
        last)
            SERVICE_PATH="${SORTED_FULL[-1]}"
            ;;
        interactive)
            echo "Multiple service bundles found for ID '$SERVICE_ID':"
            idx=1
            for p in "${SORTED_FULL[@]}"; do
                echo "[$idx] $(basename "$p") -> $p"
                idx=$((idx+1))
            done
            echo "Enter number of the service to use (or 0 to abort):"
            read -r choice
            if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
                echo "Invalid selection."; exit 3
            fi
            if [ "$choice" -eq 0 ]; then
                echo "Aborted by user."; exit 4
            fi
            if [ "$choice" -lt 1 ] || [ "$choice" -gt ${#SORTED_FULL[@]} ]; then
                echo "Selection out of range."; exit 5
            fi
            SERVICE_PATH="${SORTED_FULL[$((choice-1))]}"
            ;;
        *)
            echo "Unknown --multiple-instances-action value: '$MULTI_ACTION'"
            echo "Supported: terminate, first, last, or omit for interactive selection."
            exit 6
            ;;
    esac
fi

# Extract base name and directory
SERVICE_BASENAME=$(basename "$SERVICE_PATH" .apprun)
SERVICE_NAME="${SERVICE_BASENAME}.service"
SERVICE_FILE_PATH="$SERVICE_PATH/$SERVICE_NAME"
APPRUN_FILE_PATH="$SERVICE_PATH/$SERVICE_BASENAME.apprun"

if [ ! -f "$SERVICE_FILE_PATH" ]; then
    echo "Service file '$SERVICE_NAME' not found in '$SERVICE_PATH'."
    exit 1
fi

function GetSetFlags() {
    # $1: Bundle path
    # $2: Action (Enable/Disable)
    CMD_FLAGS=""
    if [ -d "$1/AppRunMeta/ControlFlags/Enable" ]; then
        for flag_file in "$1/AppRunMeta/ControlFlags/Enable"/*; do
            flag_name=$(basename "$flag_file")
            flag_value=$(cat "$flag_file")
            if [ -z "$flag_value" ]; then
                CMD_FLAGS+=" --$flag_name"
            else
                CMD_FLAGS+=" --$flag_name=\"$flag_value\""
            fi
        done
    fi
    echo "$CMD_FLAGS"
}

case $ACTION in
    enable)
        echo "Enabling service '$SERVICE_NAME'..."

        # Prepare the apprun environment
        /usr/bin/apprun-prepare.sh "$APPRUN_FILE_PATH"

        # If bundle contains "AppRunMeta/ControlFlags" directory, iterate through it and put it to systemctl command
        # File name is key, content is value
        # If file is empty, just use the key as flag
        CMD_FLAGS=$(GetSetFlags "$APPRUN_FILE_PATH" "Enable")

        # Enable and start the service
        sudo systemctl $CMD_FLAGS enable "$SERVICE_FILE_PATH"
        sudo systemctl $CMD_FLAGS start "$SERVICE_NAME"

        echo "Service '$SERVICE_NAME' enabled and started."
        ;;
    disable)
        echo "Disabling service '$SERVICE_NAME'..."

        # If bundle contains "AppRunMeta/ControlFlags" directory, iterate through it and put it to systemctl command
        # File name is key, content is value
        # If file is empty, just use the key as flag
        CMD_FLAGS=$(GetSetFlags "$APPRUN_FILE_PATH" "Disable")

        # Stop and disable the service
        sudo systemctl $CMD_FLAGS stop "$SERVICE_BASENAME"
        sudo systemctl $CMD_FLAGS disable "$SERVICE_NAME"

        echo "Service '$SERVICE_NAME' stopped and disabled."
        ;;
    restart)
        echo "Restarting service '$SERVICE_NAME'..."
        CMD_FLAGS=$(GetSetFlags "$APPRUN_FILE_PATH" "Disable")
#        sudo systemctl restart "$SERVICE_NAME"
        sudo systemctl $CMD_FLAGS stop "$SERVICE_NAME"
        sudo systemctl $CMD_FLAGS disable "$SERVICE_NAME"
        CMD_FLAGS=$(GetSetFlags "$APPRUN_FILE_PATH" "Enable")
        sudo systemctl $CMD_FLAGS enable "$SERVICE_FILE_PATH"
        sudo systemctl $CMD_FLAGS start "$SERVICE_NAME"
        echo "Service '$SERVICE_NAME' restarted."
        ;;
    status)
        echo "Status of service '$SERVICE_NAME':"
        sudo systemctl status "$SERVICE_NAME"
        ;;

    logs)
        echo "Logs of service '$SERVICE_NAME':"
        sudo journalctl -u "$SERVICE_NAME" --no-pager
        ;;
    journal)
        echo "Journal logs of service '$SERVICE_NAME':"
        sudo journalctl -xeu "$SERVICE_NAME"
        ;;
    name)
        echo "$SERVICE_NAME"
        ;;
esac