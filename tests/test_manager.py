import unittest
import os
import subprocess
import time
import yaml
import shutil
import fcntl
from concurrent.futures import ThreadPoolExecutor

class TestManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/tmp_manager"
        os.makedirs(self.test_dir, exist_ok=True)
        self.config_path = os.path.join(self.test_dir, "config.yaml")
        self.sources_path = os.path.join(self.test_dir, "sources.yaml")
        self.dummy_script = os.path.join(self.test_dir, "dummy_gateway.py")
        self.lock_file = "manager.lock"

        # Create a dummy config
        config = {
            'manager': {
                'max_parallel_processes': 2,
                'script_to_run': self.dummy_script
            }
        }
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f)

        # Create a dummy sources.yaml
        sources = {
            'sources': [
                {'sourceid': 'source1'},
                {'sourceid': 'source2'},
                {'sourceid': 'source3'}
            ]
        }
        with open(self.sources_path, 'w') as f:
            yaml.dump(sources, f)

        # Create a dummy gateway script that just sleeps and prints
        with open(self.dummy_script, 'w') as f:
            f.write("import argparse\n")
            f.write("import time\n")
            f.write("parser = argparse.ArgumentParser()\n")
            f.write("parser.add_argument('--source')\n")
            f.write("parser.add_argument('--limit', type=int)\n")
            f.write("parser.add_argument('--dry-run', action='store_true')\n")
            f.write("args = parser.parse_args()\n")
            f.write("print(f'Running {args.source}')\n")
            f.write("time.sleep(0.5)\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.lock_file):
            os.remove(self.lock_file)

    def test_manager_run(self):
        # We need to run manager.py, but it expects config.yaml and sources.yaml in the current dir
        # or we pass --config. However, it currently hardcodes sources.yaml path.
        # Let's temporarily copy files to root or mock them.
        # Actually, manager.py loads sources.yaml from the current directory.
        
        # Backup existing files if they exist
        backups = {}
        for f in ['config.yaml', 'sources.yaml']:
            if os.path.exists(f):
                backups[f] = f + ".bak"
                shutil.move(f, backups[f])
        
        try:
            shutil.copy(self.config_path, 'config.yaml')
            shutil.copy(self.sources_path, 'sources.yaml')
            
            result = subprocess.run(['python3', 'manager.py'], capture_output=True, text=True)
            if result.returncode != 0:
                print("Manager output:", result.stdout)
                print("Manager error:", result.stderr)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Loaded 3 items from sources.yaml", result.stdout)
            self.assertIn("[DONE] source1 (Success)", result.stdout)
            self.assertIn("[DONE] source2 (Success)", result.stdout)
            self.assertIn("[DONE] source3 (Success)", result.stdout)
        finally:
            # Restore backups
            for f in ['config.yaml', 'sources.yaml']:
                if os.path.exists(f):
                    os.remove(f)
                if f in backups:
                    shutil.move(backups[f], f)

    def test_singleton_lock(self):
        # Manually acquire the lock
        # Use 'a' mode as in manager.py
        lock_file_handle = open(self.lock_file, 'a')
        fcntl.flock(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        try:
            result = subprocess.run(['python3', 'manager.py'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Error: Another instance of manager.py is already running.", result.stdout)
        finally:
            fcntl.flock(lock_file_handle, fcntl.LOCK_UN)
            lock_file_handle.close()

if __name__ == '__main__':
    unittest.main()
