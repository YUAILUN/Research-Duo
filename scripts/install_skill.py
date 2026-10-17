#!/usr/bin/env python3
"""Install the self-contained skill; explicit replacements retain a backup."""
import argparse
import datetime as dt
import os
from pathlib import Path
import shutil
import tempfile


def install(destination, replace=False):
    source = Path(__file__).resolve().parents[1] / "skills" / "research-duo"
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink():
        raise ValueError("Refusing to replace a symlink; choose a directory destination")
    if destination.exists() and not replace:
        raise ValueError(f"Already installed: {destination}. Use --replace to retain a backup and update.")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Installation destination must be outside the source tree")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".research-duo-", dir=destination.parent) as tmp:
        staged = Path(tmp) / "research-duo"
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        backup = None
        if destination.exists():
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = destination.with_name(destination.name + ".backup-" + stamp)
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup is not None:
                backup.rename(destination)
            raise
    return destination, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills" / "research-duo"
    parser.add_argument("--destination", type=Path, default=default)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        destination, backup = install(args.destination, args.replace)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(f"Installed: {destination}")
    if backup:
        print(f"Previous version retained: {backup}")


if __name__ == "__main__":
    main()
