#!/usr/bin/env python3
"""Check portable resources, local links, local-only dependencies and synthetic cases."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-duo"
sys.path.insert(0, str(SKILL / "scripts"))
from contracts import load_json
from decision_tools import audit, calibrate, gate, rank, robust, voi


def main():
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\nname: research-duo\ndescription: ")
    assert len(content.splitlines()) < 150
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
            if SKILL in path.parents:
                assert SKILL == target or SKILL in target.parents, f"Skill dependency escapes package: {path}: {link}"
    allowed = {"argparse", "json", "math", "sys", "pathlib", "contracts", "decision_math", "evidence_graph"}
    for script in (SKILL / "scripts").glob("*.py"):
        for node in ast.walk(ast.parse(script.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            assert set(names) <= allowed, f"Unexpected runtime dependency: {script}: {names}"
    assert not (SKILL / "scripts" / "jev_client.py").exists()
    lenses = (SKILL / "references" / "lenses.md").read_text(encoding="utf-8")
    ids = re.findall(r"^\| (L\d{2}) \|", lenses, re.M)
    assert len(ids) == len(set(ids)) == 80
    data = lambda name: load_json(SKILL / "assets" / (name + "-example.json"))
    result = gate(data("gate"))
    assert result["route"] == "reframe" and result["execute"] is False
    assert rank(data("ranking"))["stable_first_choice"] is True
    assert calibrate(data("calibration"))["n"] == 6
    assert voi(data("voi"))["experiments"][0]["net_value"] == 25
    assert robust(data("robust"))["minimax_regret_actions"] == ["bounded_pilot"]
    assert audit(data("evidence-graph"))["decisions_to_revisit"] == ["D1"]
    cases = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text().splitlines()]
    assert len(cases) == len({c["id"] for c in cases}) == 8
    assert all(c["prompt"] for c in cases)
    print("Package OK: portable links, 80 lenses, 6 executable examples, 8 evaluation prompts, local-only imports.")


if __name__ == "__main__":
    main()
