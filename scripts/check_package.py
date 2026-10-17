#!/usr/bin/env python3
"""Check distributable resources, local Markdown links and synthetic inputs."""
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-duo"
sys.path.insert(0, str(SKILL / "scripts"))
from jev_client import load_json, validate_request
from decision_tools import gate, rank, calibrate


def main():
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\nname: research-duo\ndescription: ")
    assert len(content.splitlines()) < 500
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        body = path.read_text(encoding="utf-8")
        assert "TODO" not in body, f"Unfinished scaffold: {path}"
        for link in re.findall(r"\]\(([^)]+)\)", body):
            if re.match(r"[a-z]+://|#", link):
                continue
            target = (path.parent / link.split("#")[0]).resolve()
            assert target.exists(), f"Broken local link: {path}: {link}"
    lenses = (SKILL / "references" / "lenses.md").read_text(encoding="utf-8")
    ids = re.findall(r"^\| (L\d{2}) \|", lenses, re.M)
    assert len(ids) == len(set(ids)) == 80
    validate_request(load_json(SKILL / "assets" / "jev-request.json"))
    result = gate(load_json(SKILL / "assets" / "gate-example.json"))
    assert result["route"] == "deliberate" and result["execute"] is False
    assert rank(load_json(SKILL / "assets" / "ranking-example.json"))["stable_first_choice"] is True
    assert calibrate(load_json(SKILL / "assets" / "calibration-example.json"))["n"] == 6
    print("Package OK: 80 lenses, local links, request contract, and synthetic examples.")


if __name__ == "__main__":
    main()
