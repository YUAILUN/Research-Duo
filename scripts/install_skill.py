#!/usr/bin/env python3
"""Install the same skill into Claude Code, Codex and Antigravity discovery paths."""
import argparse
import datetime as dt
from pathlib import Path
import shutil
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / "skills" / "research-duo"
TARGETS = ("all", "codex", "claude", "antigravity", "antigravity-cli", "antigravity-legacy", "codex-legacy")


def destinations(target="all", project=None, home=None):
    base = Path(home or Path.home()).expanduser()
    if project is not None:
        base = Path(project).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("Project directory must already exist")
        locations = {
            "codex": ".agents/skills", "claude": ".claude/skills",
            "antigravity": ".agents/skills", "antigravity-cli": ".agents/skills",
            "antigravity-legacy": ".agent/skills", "codex-legacy": ".codex/skills",
        }
    else:
        locations = {
            "codex": ".agents/skills", "claude": ".claude/skills",
            "antigravity": ".gemini/config/skills", "antigravity-cli": ".gemini/antigravity-cli/skills",
            "antigravity-legacy": ".gemini/antigravity/skills", "codex-legacy": ".codex/skills",
        }
    selected = ("codex", "claude", "antigravity") if target == "all" else (target,)
    # Codex and Antigravity share the canonical project directory.
    return list(dict.fromkeys(base / locations[t] / "research-duo" for t in selected))


def preflight(destination, replace=False):
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink():
        raise ValueError("Refusing to replace a symlink; choose a directory destination")
    destination = destination.resolve()
    if destination.exists() and not destination.is_dir():
        raise ValueError("Destination must be a directory")
    if destination.exists() and not replace:
        raise ValueError(f"Already installed: {destination}. Use --replace to retain a backup and update.")
    if SOURCE == destination or SOURCE in destination.parents or destination in SOURCE.parents:
        raise ValueError("Installation destination must be outside the source tree")
    return destination


def install(destination, replace=False):
    destination = preflight(destination, replace)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Staging and backups stay OUTSIDE the scanned skills directory.
    workspace = destination.parent.parent
    with tempfile.TemporaryDirectory(prefix=".research-duo-stage-", dir=workspace) as tmp:
        staged = Path(tmp) / "research-duo"
        shutil.copytree(SOURCE, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        backup = None
        if destination.exists():
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = workspace / "skill-backups" / (destination.name + "-" + stamp)
            backup.parent.mkdir(parents=True, exist_ok=True)
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
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--target", choices=TARGETS)
    group.add_argument("--destination", type=Path, help="custom skill directory, including research-duo")
    parser.add_argument("--project", type=Path, help="existing project directory instead of personal installation")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        if args.destination and args.project:
            raise ValueError("--destination and --project cannot be combined")
        paths = [args.destination] if args.destination else destinations(args.target or "all", args.project)
        paths = [preflight(path, args.replace) for path in paths]
        for path in paths:
            destination, backup = install(path, args.replace)
            print(f"Installed: {destination}")
            if backup:
                print(f"Previous version retained outside skill discovery: {backup}")
    except (OSError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
