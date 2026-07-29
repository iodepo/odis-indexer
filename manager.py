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
    It starts the external python script as a subprocess and streams output.
    """
    print(f"[STARTING] {item_name}", flush=True)
    try:
        # Construct the command: python3 script_to_run.py --source item_name [extra_args]
        cmd = [sys.executable, script_path, '--source', item_name]
        cmd.extend(extra_args)
        
        # Using Popen to stream output or at least not capture it all at once if we want to see it in real-time
        # However, to avoid interleaving issues when running in parallel, 
        # it might be better to just let it inherit stdout/stderr if we are okay with interleaving,
        # OR we capture it and print it as it comes.
        # But since the user wants to see it in the log, they probably want it as it's produced.
        
        # If we use subprocess.run with capture_output=False (default), it goes to the parent's stdout.
        # But then multiple processes will interleave their output.
        # Given the manager.log redirection, interleaving might be confusing but at least it shows up.
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        for line in process.stdout:
            print(f"[{item_name}] {line}", end="", flush=True)
            
        process.wait()
        
        if process.returncode == 0:
            return f"[DONE] {item_name} (Success)"
        else:
            return f"[FAILED] {item_name} - Exit code: {process.returncode}"
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
        print("Error: Another instance of manager.py is already running.", flush=True)
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
        print(f"Error: {config_file} not found.", flush=True)
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
        print(f"Error: {sources_file} not found.", flush=True)
        return

    sources = sources_data.get('sources', [])
    items = [s['sourceid'] for s in sources if 'sourceid' in s and s.get('active', True)]

    print(f"Loaded {len(items)} items from sources.yaml. Concurrency limit: {max_workers}\n", flush=True)

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
                print(status_message, flush=True)
            except Exception as e:
                print(f"[CRITICAL] {item} generated an unhandled exception: {e}", flush=True)

    print("\nAll processes have finished.", flush=True)

if __name__ == "__main__":
    main()