"""
Gateway script to execute summoner, scribe, and indexer in sequence.
"""

import argparse
import sys
import logging
from pathlib import Path

# Import main functions from the modules
# We use absolute imports assuming the script is run with PYTHONPATH=.
def get_summoner_main():
    from summoner.__main__ import main
    return main

def get_scribe_main():
    from scribe.__main__ import main
    return main

def get_indexer_main():
    from indexer.__main__ import main
    return main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gateway",
        description="ODIS indexer all in one: Execute summoner, scribe and indexer in sequence.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Source name to process",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max objects to process (smoke tests)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: do not write to stores",
    )
    parser.add_argument(
        "--rude",
        action="store_true",
        help="Ignore robots.txt (summoner only)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    return parser

def main() -> int:
    parser = build_parser()
    # We want to pass the relevant arguments to each script.
    # Some scripts might not support all arguments, so we'll filter or pass what's needed.
    args, unknown = parser.parse_known_args()

    if unknown:
        print(f"Warning: Unknown arguments ignored: {unknown}")

    # Prepare argv for sub-scripts
    # We reconstruct argv to pass to the main functions of each module
    common_args = []
    if args.config:
        common_args.extend(["--config", str(args.config)])
    if args.source:
        common_args.extend(["--source", args.source])
    if args.limit:
        common_args.extend(["--limit", str(args.limit)])
    if args.dry_run:
        common_args.append("--dry-run")
    if args.verbose:
        common_args.append("--verbose")

    # 1. Summoner
    print("\n>>> Running Summoner...")
    summoner_args = list(common_args)
    if args.rude:
        summoner_args.append("--rude")
    
    try:
        summoner_main = get_summoner_main()
        rc = summoner_main(summoner_args)
    except Exception as e:
        print(f"Error executing Summoner: {e}")
        return 1

    if rc != 0:
        print(f"Summoner failed with exit code {rc}")
        return rc

    # 2. Scribe
    print("\n>>> Running Scribe...")
    scribe_args = list(common_args)
    # Scribe doesn't support --rude, common_args doesn't have it.
    try:
        scribe_main = get_scribe_main()
        rc = scribe_main(scribe_args)
    except Exception as e:
        print(f"Error executing Scribe: {e}")
        return 1

    if rc != 0:
        print(f"Scribe failed with exit code {rc}")
        return rc

    # 3. Indexer
    print("\n>>> Running Indexer...")
    indexer_args = list(common_args)
    # Indexer doesn't support --rude, common_args doesn't have it.
    try:
        indexer_main = get_indexer_main()
        rc = indexer_main(indexer_args)
    except Exception as e:
        print(f"Error executing Indexer: {e}")
        return 1

    if rc != 0:
        print(f"Indexer failed with exit code {rc}")
        return rc

    print("\nGateway: All steps completed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
