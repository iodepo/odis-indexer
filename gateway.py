"""
Gateway script to execute summoner, scribe, and indexer in sequence.
"""

import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

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

def get_summoner_config_loader():
    from summoner.config import load_config
    return load_config

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
        help="Source ID to process, or 'all' to process all active sources",
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

    # Setup logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")

    # Determine sources to process
    sources = []
    if args.source == "all":
        load_config = get_summoner_config_loader()
        # Same default logic as in summoner.__main__
        config_path = args.config
        if not config_path:
            root_dir = Path(__file__).resolve().parent
            candidate = root_dir / "config.yaml"
            config_path = candidate if candidate.is_file() else Path("config.yaml")
        
        try:
            cfg = load_config(config_path)
            sources = [s.sourceid for s in cfg.sources if s.active]
        except Exception as e:
            print(f"Error loading config to find all sources: {e}")
            return 1
        
        if not sources:
            print("No active sources found.")
            return 0
        print(f"Processing all active sources: {', '.join(sources)}")
    else:
        sources = [args.source]

    overall_rc = 0
    for sourceid in sources:
        log_file = log_dir / f"gateway_{sourceid}_{today}.log"
        print(f"\n{'='*60}")
        print(f"Processing source: {sourceid}")
        print(f"Logging to: {log_file}")
        print(f"{'='*60}")
        
        # Configure logging to file for this source
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))

        root_logger = logging.getLogger()
        # Remove existing handlers if any (from previous iterations)
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        if args.verbose:
            root_logger.setLevel(logging.DEBUG)
        else:
            root_logger.setLevel(logging.INFO)

        # Prepare argv for sub-scripts
        # We reconstruct argv to pass to the main functions of each module
        common_args = []
        if args.config:
            common_args.extend(["--config", str(args.config)])
        
        common_args.extend(["--source", sourceid])
        
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
            print(f"Error executing Summoner for {sourceid}: {e}")
            overall_rc = 1
            # We continue to Indexer even if Summoner fails to ensure stats are updated
            rc = 1 

        if rc != 0:
            print(f"Summoner failed for {sourceid} with exit code {rc}")
            overall_rc = rc
            # Continue to Indexer anyway

        # 2. Scribe
        print("\n>>> Running Scribe...")
        scribe_args = list(common_args)
        # Scribe doesn't support --rude, common_args doesn't have it.
        try:
            scribe_main = get_scribe_main()
            rc_scribe = scribe_main(scribe_args)
        except Exception as e:
            print(f"Error executing Scribe for {sourceid}: {e}")
            overall_rc = 1
            rc_scribe = 1

        if rc_scribe != 0:
            print(f"Scribe failed for {sourceid} with exit code {rc_scribe}")
            overall_rc = rc_scribe
            # Continue to Indexer anyway

        # 3. Indexer
        print("\n>>> Running Indexer...")
        indexer_args = list(common_args)
        # Indexer doesn't support --rude, common_args doesn't have it.
        try:
            indexer_main = get_indexer_main()
            rc = indexer_main(indexer_args)
        except Exception as e:
            print(f"Error executing Indexer for {sourceid}: {e}")
            overall_rc = 1
            continue

        if rc != 0:
            print(f"Indexer failed for {sourceid} with exit code {rc}")
            overall_rc = rc
            continue

    if overall_rc == 0:
        print("\nGateway: All steps completed successfully for all sources.")
    else:
        print(f"\nGateway: Completed with errors. Last non-zero exit code: {overall_rc}")
    
    return overall_rc

if __name__ == "__main__":
    sys.exit(main())
