#!/usr/bin/env python3
import sys
import argparse
from oscore.libsnapshot import BtrfsSnapshotManager, SnapshotError

def main():
    parser = argparse.ArgumentParser(description="Btrfs Snapshot Manager (Python Refactor)")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: create
    parser_create = subparsers.add_parser("create", help="Create a new snapshot (Options: --name, --mode [bootable|integrity|sandbox])")
    parser_create.add_argument("--mode", choices=["bootable", "integrity", "sandbox"], default="sandbox", help="Snapshot mode")
    parser_create.add_argument("--name", help="Optional label for the snapshot")

    # Command: list
    parser_list = subparsers.add_parser("list", help="List available snapshots")
    parser_list.add_argument("--update-grub", action="store_true", help="Force update of GRUB menu")

    # Command: delete
    parser_delete = subparsers.add_parser("delete", help="Delete a snapshot")
    parser_delete.add_argument("target", help="Name of snapshot to delete")

    # Command: restore
    parser_restore = subparsers.add_parser("restore", help="Restore system from snapshot")
    parser_restore.add_argument("target", help="Name of snapshot to restore from")

    args = parser.parse_args()

    try:
        mgr = BtrfsSnapshotManager()

        if args.command == "create":
            name = mgr.create_snapshot(mode=args.mode, name=args.name)
            print(f"[+] Snapshot created successfully: {name}")

        elif args.command == "list":
            snaps = mgr.enumerate_snapshots(update_grub=args.update_grub)
            print(f"{'Snapshot Name':<40} | {'Type':<10} | {'Kernel':<10}")
            print("-" * 65)
            for s in snaps:
                try:
                    print(f"{s['name']:<40} | {s['type']:<10} | {s['kernel']:<10}")
                except:
                    print(f"{s['name']:<40} | {'N/A':<10} | {'N/A':<10}")

        elif args.command == "delete":
            mgr.delete_snapshot(args.target)
            print("[+] Snapshot deleted.")

        elif args.command == "restore":
            print("WARNING: This will overwrite your current system.")
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() == "yes":
                mgr.restore_snapshot(args.target)
            else:
                print("Aborted.")

        else:
            parser.print_help()

    except SnapshotError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

