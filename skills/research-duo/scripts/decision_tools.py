#!/usr/bin/env python3
"""Deterministic advisory routing, transparent ranking and binary calibration."""
import argparse
import json
import math
import sys
from jev_client import load_json, number, require, text, validate_answer


def gate(context):
    require(isinstance(context, dict), "gate context must be an object")
    require(context.get("risk") in ("low", "medium", "high"), "invalid risk")
    require(context.get("evidence_status") in ("verified", "partial", "missing", "conflicted"), "invalid evidence status")
    for key in ("in_distribution", "reversible"):
        require(type(context.get(key)) is bool, f"{key}: boolean required")
    require(context.get("provider") in ("jev", "llm", "human", "fixture"), "invalid provider")
    for key in ("model", "question_set_id"):
        text(context.get(key), key)
    answer = context.get("answer")
    require(isinstance(answer, dict), "answer required")
    probs = answer.get("probabilities")
    require(isinstance(probs, dict) and 2 <= len(probs) <= 255, "Choice distribution required")
    require(all(isinstance(k, str) and k.strip() for k in probs), "option IDs required")
    validate_answer({"type": "choice", "criteria": {k: None for k in probs}}, answer)
    policy = context.get("policy")
    require(isinstance(policy, dict), "policy required")
    min_p = number(policy.get("min_probability"), "min_probability", 0.5, 1)
    min_margin = number(policy.get("min_margin"), "min_margin")
    abstain = context.get("abstain_options")
    require(isinstance(abstain, list) and all(isinstance(x, str) for x in abstain), "abstain_options must be a string array")
    require(set(abstain) <= set(probs), "abstain option outside distribution")
    calibration = context.get("calibration")
    require(isinstance(calibration, dict) and type(calibration.get("validated")) is bool, "calibration.validated must be boolean")
    ordered = sorted(probs.values(), reverse=True)
    p, margin = ordered[0], ordered[0] - ordered[1]
    route, reason = "recommend", "validated_low_risk_advisory_candidate"
    if context["risk"] == "high" or not context["reversible"]:
        route, reason = "review", "high_impact_or_irreversible"
    elif context["evidence_status"] in ("missing", "partial"):
        route, reason = "gather_evidence", "decisive_evidence_incomplete"
    elif context["evidence_status"] == "conflicted":
        route, reason = "deliberate", "resolve_material_conflict"
    elif not context["in_distribution"]:
        route, reason = "review", "outside_validated_scope"
    elif (context["provider"] != "jev" or not calibration["validated"]
          or context["model"] in ("jev-latest", "jev-preview")
          or calibration.get("model") != context["model"]
          or calibration.get("question_set_id") != context["question_set_id"]
          or not isinstance(calibration.get("validation_ref"), str)
          or not calibration["validation_ref"].strip()):
        route, reason = "review", "no_matching_domain_validation"
    elif answer["choice"] in abstain:
        route, reason = "deliberate", "explicit_abstention"
    elif p < min_p or margin < min_margin or math.isclose(margin, 0, abs_tol=1e-12):
        route, reason = "deliberate", "uncertain_or_near_tie"
    return {"route": route, "reason": reason, "choice": answer["choice"],
            "top_probability": p, "margin": margin, "execute": False,
            "notice": "Advisory only; input declarations require independent verification."}


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
    parser.add_argument("command", choices=("gate", "rank", "calibrate"))
    parser.add_argument("input")
    parser.add_argument("--bins", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    try:
        data = load_json(args.input)
        result = calibrate(data, args.bins, args.threshold) if args.command == "calibrate" else {"gate": gate, "rank": rank}[args.command](data)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RecursionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
