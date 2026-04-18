"""
deploy_demo.py
==============
Builds the GitHub Pages demo dataset and commits it.

Steps:
  1. Runs build_demo_json.py  →  data.demo.json, admin_data.demo.json
  2. Copies those files to data.json and admin_data.json (GitHub Pages reads these)
  3. Runs git add + commit + push

Your local data.json is restored automatically after the push.

Run from the project root:
    python deploy_demo.py
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(__file__)

DEMO_DATA  = os.path.join(ROOT, "data.demo.json")
DEMO_ADMIN = os.path.join(ROOT, "admin_data.demo.json")
LIVE_DATA  = os.path.join(ROOT, "data.json")
LIVE_ADMIN = os.path.join(ROOT, "admin_data.json")
BUILD_DATA = os.path.join(ROOT, "build_data_json.py")
BUILD_DEMO = os.path.join(ROOT, "build_demo_json.py")


def run(cmd, **kwargs):
    result = subprocess.run(cmd, shell=True, **kwargs)
    if result.returncode != 0:
        print(f"ERROR: command failed: {cmd}")
        sys.exit(1)


def main():
    print("=== Step 1: Build demo dataset ===")
    run(f'python "{BUILD_DEMO}"')

    if not os.path.exists(DEMO_DATA):
        print(f"ERROR: {DEMO_DATA} not found after build")
        sys.exit(1)

    print()
    print("=== Step 2: Copy demo files to data.json / admin_data.json ===")
    shutil.copy2(DEMO_DATA, LIVE_DATA)
    shutil.copy2(DEMO_ADMIN, LIVE_ADMIN)
    print(f"  Copied data.demo.json      → data.json")
    print(f"  Copied admin_data.demo.json → admin_data.json")

    print()
    print("=== Step 3: Commit and push to GitHub ===")
    run('git add data.json admin_data.json')
    run('git commit -m "Update demo dataset for GitHub Pages"')
    run('git push origin main')

    print()
    print("=== Step 4: Restore local full dataset ===")
    run(f'python "{BUILD_DATA}"')

    print()
    print("Done. GitHub Pages has the demo dataset; local site has full data.")


if __name__ == "__main__":
    main()
