# this script should be the starting point of the complete indexing process
# it will get the sourceids from the sources.yaml file
# and pass this id to the gateway script that will summon, index and scribe what is found
# this script will limit the number of processes that run in parallel
# using a config setting in config.yaml

import yaml
import subprocess
import time
import argparse
import sys
import os
import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed

LOCK_FILE = "manager.lock"

def run_task(item_name, script_path, extra_args):
    """
    Function executed by the worker threads.
    It starts the external python script as a subprocess.
    """
    print(f"[STARTING] {item_name}")
    try:
        # Construct the command: python3 script_to_run.py --source item_name [extra_args]
        # gateway.py expects --source (or -s)
        # Ensure we are using the absolute path of the script
        cmd = [sys.executable, script_path, '--source', item_name]
        cmd.extend(extra_args)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return f"[DONE] {item_name} (Success)"
    except subprocess.CalledProcessError as e:
        return f"[FAILED] {item_name} - Error: {e.stderr.strip()}"
    except Exception as e:
        return f"[ERROR] {item_name} - {str(e)}"

def main():
    # Singleton check using file lock
    # Get the directory of the current script (manager.py)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    lock_file_path = os.path.join(base_dir, LOCK_FILE)

    # We open in 'a' mode and keep the handle open to ensure the lock is held
    try:
        lock_file_handle = open(lock_file_path, 'a')
        fcntl.flock(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print("Error: Another instance of manager.py is already running.")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="manager",
        description="ODIS manager: Execute gateway for multiple sources in parallel.",
    )
    parser.add_argument(
        "--config",
        "-c",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--limit",
        type=int,
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

    args = parser.parse_args()

    # Prepare extra arguments to pass to gateway.py
    extra_args = []
    if args.config:
        extra_args.extend(['--config', args.config])
    if args.limit is not None:
        extra_args.extend(['--limit', str(args.limit)])
    if args.dry_run:
        extra_args.append('--dry-run')
    if args.rude:
        extra_args.append('--rude')
    if args.verbose:
        extra_args.append('--verbose')

    # 1. Load configuration
    config_file = args.config if args.config else os.path.join(base_dir, 'config.yaml')
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: {config_file} not found.")
        return

    manager_config = config.get('manager', {})
    max_workers = manager_config.get('max_parallel_processes', 1)
    
    script_to_run = manager_config.get('script_to_run', 'gateway.py')
    
    # If the script_to_run is not an absolute path, make it relative to base_dir
    if not os.path.isabs(script_to_run):
        script_to_run = os.path.join(base_dir, script_to_run)

    # 2. Load sources
    # We might want to use sources.yaml path from config, but for now it's hardcoded as per previous state
    sources_file = os.path.join(base_dir, 'sources.yaml')
    try:
        with open(sources_file, 'r') as f:
            sources_data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: {sources_file} not found.")
        return

    sources = sources_data.get('sources', [])
    items = [s['sourceid'] for s in sources if 'sourceid' in s]

    print(f"Loaded {len(items)} items from sources.yaml. Concurrency limit: {max_workers}\n")

    # 3. Use ThreadPoolExecutor to manage parallel execution
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(run_task, item, script_to_run, extra_args): item
            for item in items
        }

        # 4. Track progress as they complete
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                status_message = future.result()
                print(status_message)
            except Exception as e:
                print(f"[CRITICAL] {item} generated an unhandled exception: {e}")

    print("\nAll processes have finished.")

if __name__ == "__main__":
    main()