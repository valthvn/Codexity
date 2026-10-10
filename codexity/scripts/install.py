#!/usr/bin/env python3
"""Install the bundled skill into an explicit local Codex skills directory."""
import argparse
from pathlib import Path
import shutil
import sys

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skills-dir", required=True, help="Skills parent directory, e.g. ~/.codex/skills or .agents/skills")
    args = p.parse_args()
    source = Path(__file__).resolve().parent.parent
    dest = Path(args.skills_dir).expanduser().resolve() / "codexity"
    if source == dest:
        print("Codexity is already installed at this location.")
        return 0
    if dest.exists():
        print("Destination already exists; no files overwritten. Choose another directory or update it deliberately.", file=sys.stderr)
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    print(f"Installed Codexity: {dest}. Open a new Codex conversation and invoke $codexity.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
