"""Finite decision analysis conditional on explicit inputs; no learned probabilities."""
import math
from contracts import number, require, strings, text


def winners(values, maximize=True):
    target = (max if maximize else min)(values.values())
    return sorted(k for k, v in values.items() if math.isclose(v, target, rel_tol=1e-12, abs_tol=1e-9))


def utilities(table, states):
    require(isinstance(table, dict) and table, "nonempty action utility table required")
    for action, row in table.items():
        text(action, "action")
        require(isinstance(row, dict) and set(row) == set(states), "utility row must cover exactly all states/scenarios")
        for state, value in row.items():
            number(value, f"utility {action}/{state}", -1e12, 1e12)


def probability(row, keys, name):
    require(isinstance(row, dict) and set(row) == set(keys), f"{name}: keys must match")
    for key, value in row.items():
        number(value, f"{name}/{key}")
    require(math.isclose(sum(row.values()), 1, rel_tol=0, abs_tol=1e-9), f"{name}: probabilities must sum to one")


def voi(data):
    require(isinstance(data, dict), "VOI input must be an object")
    text(data.get("utility_unit"), "utility_unit")
    require(data.get("basis") in ("empirical", "elicited", "hypothetical"), "probability basis required")
    assumptions = data.get("assumptions")
    require(isinstance(assumptions, dict), "assumptions required")
    for key in ("priors", "likelihoods", "utilities"):
        text(assumptions.get(key), f"assumptions.{key}")
    priors = data.get("priors")
    require(isinstance(priors, dict) and priors, "priors required; use robust when probabilities are unknown")
    for state in priors:
        text(state, "state")
    probability(priors, priors, "priors")
    table = data.get("utilities")
    utilities(table, priors)
    baseline = {a: sum(priors[s] * row[s] for s in priors) for a, row in table.items()}
    best = max(baseline.values())
    evpi = max(0.0, sum(priors[s] * max(row[s] for row in table.values()) for s in priors) - best)
    experiments = data.get("experiments")
    require(isinstance(experiments, list), "experiments must be an array")
    ids, results = {"no_experiment"}, []
    for experiment in experiments:
        require(isinstance(experiment, dict), "experiment must be an object")
        eid = text(experiment.get("id"), "experiment id")
        require(eid not in ids, "duplicate or reserved experiment id")
        ids.add(eid)
        cost = number(experiment.get("cost"), "cost in utility units", 0, 1e12)
        likelihoods = experiment.get("likelihoods")
        require(isinstance(likelihoods, dict) and set(likelihoods) == set(priors), "likelihoods must cover all states")
        first = next(iter(likelihoods.values()))
        require(isinstance(first, dict) and first, "nonempty outcome distribution required")
        outcomes = list(first)
        for outcome in outcomes:
            text(outcome, "outcome")
        for state, row in likelihoods.items():
            probability(row, outcomes, f"likelihoods/{state}")
        expected_best, branches = 0.0, []
        for outcome in outcomes:
            mass = sum(priors[s] * likelihoods[s][outcome] for s in priors)
            if mass == 0:
                branches.append({"outcome": outcome, "probability": 0, "posterior": None, "best_actions": []})
                continue
            posterior = {s: priors[s] * likelihoods[s][outcome] / mass for s in priors}
            expected = {a: sum(posterior[s] * row[s] for s in priors) for a, row in table.items()}
            expected_best += mass * max(expected.values())
            branches.append({"outcome": outcome, "probability": mass, "posterior": posterior,
                             "action_utilities": expected, "best_actions": winners(expected)})
        evsi = max(0.0, expected_best - best)
        results.append({"id": eid, "evsi": evsi, "cost": cost, "net_value": evsi - cost, "branches": branches})
    net = {"no_experiment": 0.0, **{r["id"]: r["net_value"] for r in results}}
    return {"baseline_utilities": baseline, "baseline_best_actions": winners(baseline), "evpi": evpi,
            "experiments": results, "preferred_experiments": winners(net), "basis": data["basis"],
            "utility_unit": data["utility_unit"], "assumptions": assumptions,
            "notice": "One-step EVSI assumes the same available actions after observing results. Input probabilities and utilities are not validated by this calculation."}


def robust(data):
    require(isinstance(data, dict), "scenario input must be an object")
    scenarios = strings(data.get("scenarios"), "scenarios", nonempty=True)
    text(data.get("utility_unit"), "utility_unit")
    text(data.get("assumptions"), "assumptions")
    table = data.get("utilities")
    utilities(table, scenarios)
    optimum = {s: max(row[s] for row in table.values()) for s in scenarios}
    regret = {a: {s: optimum[s] - row[s] for s in scenarios} for a, row in table.items()}
    worst = {a: max(row.values()) for a, row in regret.items()}
    floors = {a: min(row.values()) for a, row in table.items()}
    return {"scenario_best_actions": {s: winners({a: row[s] for a, row in table.items()}) for s in scenarios},
            "regret": regret, "maximum_regret": worst, "minimax_regret_actions": winners(worst, False),
            "minimum_utility": floors, "maximin_actions": winners(floors), "utility_unit": data["utility_unit"],
            "notice": "No probabilities assumed. Results depend on scenario coverage, utility scale and the chosen attitude toward regret."}
