#!/usr/bin/env python3
"""Local decision contracts, evidence tracing, utility analysis and calibration."""
import argparse
import json
import math
import sys
from contracts import load_json, number, require, strings, text, validate_judgment, valid_value
from decision_math import robust, voi
from evidence_graph import audit


def gate(context):
    require(isinstance(context, dict), "gate context must be an object")
    text(context.get("decision_id"), "decision_id")
    choices = {
        "risk": ("low", "medium", "high"),
        "framing_status": ("sound", "needs_reframe"),
        "evidence_status": ("verified", "partial", "missing", "conflicted"),
        "distribution_shift": ("none", "possible", "unknown"),
        "decision_stability": ("stable", "sensitive", "untested"),
    }
    for key, allowed in choices.items():
        require(context.get(key) in allowed, f"invalid {key}")
    require(type(context.get("reversible")) is bool, "reversible must be boolean")
    evidence = strings(context.get("evidence_ids"), "evidence_ids")
    judgments = context.get("judgments")
    require(isinstance(judgments, list) and judgments, "judgments required")
    by_id = {}
    for item in judgments:
        validate_judgment(item, evidence)
        require(item["id"] not in by_id, "duplicate judgment id")
        by_id[item["id"]] = item
    requirements = context.get("requirements")
    require(isinstance(requirements, dict) and requirements, "explicit decision requirements needed")
    for jid, accepted in requirements.items():
        require(jid in by_id, "required judgment missing")
        require(isinstance(accepted, list) and accepted, "accepted_values must be nonempty")
        require(all(valid_value(by_id[jid], v) for v in accepted), "accepted value outside judgment type")
    needed = [by_id[jid] for jid in requirements]
    blockers = []

    def block(condition, route, reason):
        if condition:
            blockers.append({"route": route, "reason": reason})

    block(context["framing_status"] == "needs_reframe", "reframe", "question_or_estimand_not_identifiable")
    block(context["risk"] == "high" or not context["reversible"], "review", "high_impact_or_irreversible")
    block(context["evidence_status"] == "conflicted" or any(j["status"] == "conflicted" for j in needed),
          "deliberate", "material_evidence_conflict")
    block(context["evidence_status"] in ("missing", "partial") or any(j["status"] == "unknown" for j in needed),
          "gather_evidence", "decisive_evidence_incomplete")
    failed = [j["id"] for j in needed if j["status"] == "grounded" and j["value"] not in requirements[j["id"]]]
    block(bool(failed), "revise_option", "required_condition_not_met")
    block(context["distribution_shift"] != "none", "review", "scope_transfer_not_established")
    block(context["decision_stability"] == "untested", "stress_test", "decision_stability_untested")
    block(context["decision_stability"] == "sensitive", "compare_scenarios", "decision_depends_on_fragile_inputs")
    block(any(j["status"] == "provisional" or j["basis"] == "assumed" for j in needed),
          "review", "decision_depends_on_unverified_judgment")
    first = blockers[0] if blockers else {"route": "recommend", "reason": "declared_conditions_satisfied"}
    return {"decision_id": context["decision_id"], **first, "blockers": blockers,
            "failed_requirements": failed, "execute": False,
            "notice": "Advisory routing only. Input claims need substantive verification; a valid schema is not scientific validation."}


def rank(data):
    require(isinstance(data, dict), "ranking input must be an object")
    weights = data.get("weights")
    require(isinstance(weights, dict) and weights, "nonempty weights required")
    for k, w in weights.items():
        text(k, "criterion")
        number(w, f"weight {k}", 0, 1e6)
    require(sum(weights.values()) > 0, "positive total weight required")
    options = data.get("options")
    require(isinstance(options, list) and options, "options required")
    seen, eligible, excluded = set(), [], []
    for option in options:
        require(isinstance(option, dict), "option must be object")
        name = option.get("id")
        text(name, "option id")
        require(name not in seen, "duplicate option id")
        seen.add(name)
        require(type(option.get("eligible")) is bool, "eligible must be boolean")
        if not option["eligible"]:
            text(option.get("exclusion_reason"), "exclusion_reason")
            excluded.append({"id": name, "reason": option["exclusion_reason"]})
            continue
        scores = option.get("scores")
        require(isinstance(scores, dict) and set(scores) == set(weights), "scores must match all criteria")
        for k, score in scores.items():
            number(score, f"score {name}/{k}")
        eligible.append(option)
    require(eligible, "no eligible options")

    def evaluate(ws):
        total = sum(ws.values())
        rows = [{"id": o["id"], "utility": sum(ws[k] * o["scores"][k] for k in ws) / total} for o in eligible]
        rows.sort(key=lambda x: (-x["utility"], x["id"]))
        winners = [r["id"] for r in rows if math.isclose(r["utility"], rows[0]["utility"], abs_tol=1e-10)]
        return {"ranking": rows, "winners": winners}

    baseline = evaluate(weights)
    scenarios = []
    for key in weights:
        for factor in (0.8, 1.2):
            changed = dict(weights)
            changed[key] *= factor
            scenarios.append({"criterion": key, "factor": factor, **evaluate(changed)})
    stable = len(baseline["winners"]) == 1 and all(s["winners"] == baseline["winners"] for s in scenarios)
    return {"baseline": baseline, "excluded": excluded, "scenarios": scenarios,
            "stable_first_choice": stable, "notice": "Utilities are not probabilities; sensitivity is local, one weight at a time."}


def calibrate(rows, bins=5, threshold=0.8):
    require(isinstance(rows, list) and rows, "nonempty labeled rows required")
    require(type(bins) is int and 1 <= bins <= 100, "bins must be 1–100")
    number(threshold, "threshold", 0.5, 1)
    require(threshold > 0.5, "threshold must be above 0.5")
    groups = [[] for _ in range(bins)]
    accepted = []
    for row in rows:
        require(isinstance(row, dict), "row must be an object")
        p = number(row.get("p"), "p")
        y = row.get("y")
        require(type(y) is int and y in (0, 1), "y must be integer 0 or 1")
        groups[min(int(p * bins), bins - 1)].append((p, y))
        if max(p, 1 - p) >= threshold:
            accepted.append(int(p >= 0.5) != y)
    n = len(rows)
    reliability, ece = [], 0.0
    for i, group in enumerate(groups):
        count = len(group)
        pred = sum(p for p, _ in group) / count if count else None
        rate = sum(y for _, y in group) / count if count else None
        if count:
            ece += count / n * abs(pred - rate)
        reliability.append({"lower": i / bins, "upper": (i + 1) / bins, "n": count,
                            "mean_probability": pred, "observed_rate": rate})
    return {"n": n, "brier": sum((r["p"] - r["y"]) ** 2 for r in rows) / n,
            "ece": ece, "bins": reliability, "threshold": threshold,
            "accepted_n": len(accepted), "coverage": len(accepted) / n,
            "selective_error": sum(accepted) / len(accepted) if accepted else None,
            "notice": "Descriptive binary evaluation only; does not certify calibration or set validated=true."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("gate", "rank", "calibrate", "voi", "robust", "audit"))
    parser.add_argument("input")
    parser.add_argument("--bins", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    try:
        data = load_json(args.input)
        result = calibrate(data, args.bins, args.threshold) if args.command == "calibrate" else {"gate": gate, "rank": rank, "voi": voi, "robust": robust, "audit": audit}[args.command](data)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RecursionError, OverflowError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
