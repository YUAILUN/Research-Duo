import copy
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-duo"
sys.path.insert(0, str(SKILL / "scripts"))
from contracts import decode, load_json, validate_judgment
from decision_tools import audit, calibrate, gate, rank, robust, voi
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts" / "install_skill.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def asset(name):
    return load_json(SKILL / "assets" / name)


def valid_context():
    data = asset("gate-example.json")
    data.update(framing_status="sound", decision_stability="stable")
    data["judgments"][0].update(value=True, rationale="Synthetic passing fixture, not research evidence.")
    return data


class ContractTests(unittest.TestCase):
    def test_nonfinite_and_duplicate_json_rejected(self):
        for raw in ('{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1,"a":2}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_three_types(self):
        judgment = valid_context()["judgments"][0]
        for kind, criteria, value in (
            ("predicate", {"true":"met", "false":"not met"}, True),
            ("choice", ["supports", "contradicts", "insufficient"], "insufficient"),
            ("ordinal", ["poor", "partial", "strong"], 1),
        ):
            with self.subTest(kind=kind):
                judgment.update(kind=kind, criteria=criteria, value=value)
                validate_judgment(judgment, ["SIM-E1"])

    def test_unknown_must_be_null(self):
        judgment = valid_context()["judgments"][0]
        judgment.update(status="unknown", value=None, evidence_ids=[])
        validate_judgment(judgment, [])
        for value in (False, 0, .5, "unknown"):
            judgment["value"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_judgment(judgment, [])

    def test_grounded_requires_evidence_and_not_assumption(self):
        for changes in ({"evidence_ids":[]}, {"basis":"assumed"}, {"value":None}):
            judgment = valid_context()["judgments"][0]
            judgment.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_judgment(judgment, ["SIM-E1"])

    def test_unknown_refs_and_duplicate_refs_rejected(self):
        for refs in (["NONEXISTENT"], ["SIM-E1", "SIM-E1"]):
            judgment = valid_context()["judgments"][0]
            judgment["evidence_ids"] = refs
            with self.assertRaises(ValueError):
                validate_judgment(judgment, ["SIM-E1"])

    def test_boolean_not_ordinal_and_numeric_not_predicate(self):
        for kind, criteria, value in (("ordinal", ["low","high"], True), ("predicate", {"true":"yes","false":"no"}, 1)):
            judgment = valid_context()["judgments"][0]
            judgment.update(kind=kind, criteria=criteria, value=value)
            with self.assertRaises(ValueError):
                validate_judgment(judgment, ["SIM-E1"])

    def test_outside_choices_rejected(self):
        judgment = valid_context()["judgments"][0]
        judgment.update(kind="choice", criteria=["A","B"], value="C")
        with self.assertRaises(ValueError):
            validate_judgment(judgment, ["SIM-E1"])

    def test_provider_fields_not_part_of_judgment_contract(self):
        judgment = valid_context()["judgments"][0]
        judgment["confidence"] = .99
        with self.assertRaises(ValueError):
            validate_judgment(judgment, ["SIM-E1"])

    def test_conflict_may_preserve_tentative_value_or_null(self):
        judgment = valid_context()["judgments"][0]
        for value in (None, True):
            judgment.update(status="conflicted", value=value)
            validate_judgment(judgment, ["SIM-E1"])


class GateTests(unittest.TestCase):
    def test_bad_framing_precedes_ranking(self):
        result = gate(asset("gate-example.json"))
        self.assertEqual(result["route"], "reframe")
        self.assertEqual(result["failed_requirements"], ["J1"])
        self.assertEqual(len(result["blockers"]), 3)
        self.assertFalse(result["execute"])

    def test_satisfied_conditions_are_advisory(self):
        result = gate(valid_context())
        self.assertEqual(result["route"], "recommend")
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["execute"])

    def test_context_routes(self):
        cases = [({"risk":"high"}, "review"), ({"reversible":False}, "review"),
                 ({"evidence_status":"conflicted"}, "deliberate"),
                 ({"evidence_status":"partial"}, "gather_evidence"),
                 ({"evidence_status":"missing"}, "gather_evidence"),
                 ({"distribution_shift":"possible"}, "review"),
                 ({"distribution_shift":"unknown"}, "review"),
                 ({"decision_stability":"untested"}, "stress_test"),
                 ({"decision_stability":"sensitive"}, "compare_scenarios")]
        for changes, route in cases:
            data = valid_context()
            data.update(changes)
            with self.subTest(changes=changes):
                result = gate(data)
                self.assertEqual(result["route"], route)
                self.assertFalse(result["execute"])

    def test_judgment_routes(self):
        for changes, route in [({"value":False}, "revise_option"),
                                ({"value":None,"status":"unknown"}, "gather_evidence"),
                                ({"status":"conflicted"}, "deliberate"),
                                ({"status":"provisional"}, "review")]:
            data = valid_context()
            data["judgments"][0].update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(gate(data)["route"], route)

    def test_irrelevant_unknown_does_not_block_known_local_decision(self):
        data = valid_context()
        extra = dict(data["judgments"][0], id="exploratory", status="unknown", value=None, evidence_ids=[])
        data["judgments"].append(extra)
        self.assertEqual(gate(data)["route"], "recommend")

    def test_missing_and_wrong_typed_requirements_rejected(self):
        for requirements in ({}, {"nonexistent":[True]}, {"J1":[1]}, {"J1":[None]}):
            data = valid_context()
            data["requirements"] = requirements
            with self.assertRaises(ValueError):
                gate(data)

    def test_invalid_context_fails_closed(self):
        for changes in ({"risk":"unknown"}, {"reversible":"false"}, {"evidence_status":"probably"}):
            data = valid_context()
            data.update(changes)
            with self.assertRaises(ValueError):
                gate(data)


class ValueOfInformationTests(unittest.TestCase):
    def test_known_bayesian_example(self):
        result = voi(asset("voi-example.json"))
        self.assertEqual(result["evpi"], 50)
        first, second = result["experiments"]
        self.assertAlmostEqual(first["evsi"], 30)
        self.assertAlmostEqual(first["net_value"], 25)
        self.assertAlmostEqual(second["evsi"], 0)
        self.assertEqual(result["preferred_experiments"], ["informative_test"])
        self.assertEqual(first["branches"][0]["posterior"], {"effective":.8,"ineffective":.2})

    def test_perfect_information_equals_upper_bound(self):
        data = asset("voi-example.json")
        data["experiments"] = [dict(data["experiments"][0], cost=0, likelihoods={
            "effective":{"positive":1,"negative":0},"ineffective":{"positive":0,"negative":1}})]
        result = voi(data)
        self.assertAlmostEqual(result["experiments"][0]["evsi"], result["evpi"])

    def test_no_experiment_can_win(self):
        data = asset("voi-example.json")
        for exp in data["experiments"]:
            exp["cost"] = 100
        self.assertEqual(voi(data)["preferred_experiments"], ["no_experiment"])

    def test_free_uninformative_experiment_ties_with_none(self):
        data = asset("voi-example.json")
        data["experiments"] = [dict(data["experiments"][1], cost=0)]
        self.assertEqual(voi(data)["preferred_experiments"], ["no_experiment", "uninformative_test"])

    def test_zero_mass_outcome_has_no_posterior(self):
        data = asset("voi-example.json")
        data["experiments"] = [dict(data["experiments"][0], likelihoods={
            state:{"certain":1,"impossible":0} for state in data["priors"]})]
        result = voi(data)
        branch = result["experiments"][0]["branches"][1]
        self.assertEqual(branch["probability"], 0)
        self.assertIsNone(branch["posterior"])
        self.assertEqual(result["experiments"][0]["evsi"], 0)

    def test_known_state_has_zero_information_value(self):
        data = asset("voi-example.json")
        data["priors"] = {"effective":1,"ineffective":0}
        result = voi(data)
        self.assertEqual(result["evpi"], 0)
        self.assertTrue(all(abs(e["evsi"]) < 1e-9 for e in result["experiments"]))

    def test_invalid_probability_models_rejected(self):
        original = asset("voi-example.json")
        invalid = []
        for priors in ({}, {"effective":.6,"ineffective":.6}, {"effective":True,"ineffective":0}):
            invalid.append(dict(original, priors=priors))
        bad = copy.deepcopy(original)
        del bad["experiments"][0]["likelihoods"]["effective"]["negative"]
        invalid.append(bad)
        for data in invalid:
            with self.assertRaises(ValueError):
                voi(data)

    def test_missing_utility_and_unsupported_cost_rejected(self):
        for change in ("missing", "negative_cost", "no_basis"):
            data = asset("voi-example.json")
            if change == "missing":
                del data["utilities"]["advance"]["ineffective"]
            elif change == "negative_cost":
                data["experiments"][0]["cost"] = -1
            else:
                del data["basis"]
            with self.assertRaises(ValueError):
                voi(data)

    def test_information_bounds_across_random_finite_models(self):
        rng = random.Random(27)
        for _ in range(80):
            data = asset("voi-example.json")
            p, sensitivity, false_positive = (rng.random() for _ in range(3))
            data["priors"] = {"effective":p,"ineffective":1-p}
            data["utilities"] = {a:{s:rng.uniform(-100,100) for s in data["priors"]} for a in ("A","B","C")}
            data["experiments"] = [dict(data["experiments"][0], likelihoods={
                "effective":{"positive":sensitivity,"negative":1-sensitivity},
                "ineffective":{"positive":false_positive,"negative":1-false_positive}})]
            result = voi(data)
            evsi = result["experiments"][0]["evsi"]
            self.assertGreaterEqual(evsi, -1e-9)
            self.assertLessEqual(evsi, result["evpi"] + 1e-9)


class ScenarioTests(unittest.TestCase):
    def test_regret_and_floor_criteria_can_disagree(self):
        result = robust(asset("robust-example.json"))
        self.assertEqual(result["maximum_regret"], {"advance":100,"defer":100,"bounded_pilot":65})
        self.assertEqual(result["minimax_regret_actions"], ["bounded_pilot"])
        self.assertEqual(result["maximin_actions"], ["defer"])

    def test_affine_common_utility_transform_preserves_choices(self):
        data = asset("robust-example.json")
        original = robust(data)
        data["utilities"] = {a:{s:7*u-35 for s,u in row.items()} for a,row in data["utilities"].items()}
        transformed = robust(data)
        self.assertEqual(original["minimax_regret_actions"], transformed["minimax_regret_actions"])
        self.assertEqual(original["maximin_actions"], transformed["maximin_actions"])

    def test_ties_preserved(self):
        data = asset("robust-example.json")
        data["utilities"] = {a:{s:0 for s in data["scenarios"]} for a in ("A","B")}
        self.assertEqual(robust(data)["minimax_regret_actions"], ["A","B"])

    def test_missing_scenario_is_not_imputed(self):
        data = asset("robust-example.json")
        del data["utilities"]["advance"]["effect_fails"]
        with self.assertRaises(ValueError):
            robust(data)


class EvidenceGraphTests(unittest.TestCase):
    def test_echoes_share_one_cluster_and_assumptions_survive(self):
        result = audit(asset("evidence-graph-example.json"))
        trace = result["trace"]["D1"]
        self.assertEqual(trace["evidence_ids"], ["E1","E2"])
        self.assertEqual(trace["declared_source_clusters"], ["same_cohort"])
        self.assertEqual(trace["assumption_ids"], ["A1"])

    def test_change_propagates_only_downstream(self):
        result = audit(asset("evidence-graph-example.json"))
        self.assertEqual(result["decisions_to_revisit"], ["D1"])
        self.assertEqual(set(result["affected_ids"]), {"E1","C1","J1","D1"})

    def test_cycles_and_dangling_refs_rejected(self):
        for deps in (["J1"], ["NONEXISTENT"], ["C1"]):
            data = asset("evidence-graph-example.json")
            data["nodes"][3]["depends_on"] = deps
            with self.assertRaises(ValueError):
                audit(data)

    def test_no_changes_no_invalidation(self):
        data = asset("evidence-graph-example.json")
        data["changed_ids"] = []
        self.assertEqual(audit(data)["decisions_to_revisit"], [])

    def test_unsupported_claim_and_duplicate_node_rejected(self):
        data = asset("evidence-graph-example.json")
        data["nodes"][3]["depends_on"] = []
        with self.assertRaises(ValueError):
            audit(data)
        data = asset("evidence-graph-example.json")
        data["nodes"].append(data["nodes"][0])
        with self.assertRaises(ValueError):
            audit(data)

class DecisionMathTests(unittest.TestCase):
    def test_hard_constraint_cannot_be_compensated(self):
        result = rank(asset("ranking-example.json"))
        self.assertEqual(result["baseline"]["winners"], ["within_lab_randomized_pilot"])
        self.assertEqual(result["excluded"][0]["id"], "immediate_full_rollout")
        self.assertAlmostEqual(result["baseline"]["ranking"][0]["utility"], .8025)

    def test_weight_change_can_flip_winner(self):
        data = {"weights": {"a": .51, "b": .49}, "options": [
            {"id": "A", "eligible": True, "scores": {"a": 1, "b": 0}},
            {"id": "B", "eligible": True, "scores": {"a": 0, "b": 1}}]}
        self.assertFalse(rank(data)["stable_first_choice"])

    def test_ties_are_preserved(self):
        data = {"weights": {"a": 1}, "options": [{"id": k, "eligible": True, "scores": {"a": .5}} for k in ("A", "B")]}
        result = rank(data)
        self.assertEqual(result["baseline"]["winners"], ["A", "B"])
        self.assertFalse(result["stable_first_choice"])

    def test_zero_weights_rejected(self):
        data = asset("ranking-example.json")
        data["weights"] = {k: 0 for k in data["weights"]}
        with self.assertRaises(ValueError):
            rank(data)

    def test_missing_score_not_imputed(self):
        data = asset("ranking-example.json")
        del data["options"][0]["scores"]["feasibility"]
        with self.assertRaises(ValueError):
            rank(data)

    def test_perfect_binary_predictions(self):
        result = calibrate([{"p": 0, "y": 0}, {"p": 1, "y": 1}])
        self.assertEqual((result["brier"], result["ece"], result["coverage"], result["selective_error"]), (0, 0, 1, 0))

    def test_overconfident_wrong_predictions(self):
        result = calibrate([{"p": 1, "y": 0}, {"p": 0, "y": 1}])
        self.assertEqual((result["brier"], result["ece"], result["selective_error"]), (1, 1, 1))

    def test_empty_acceptance_has_no_error_estimate(self):
        result = calibrate([{"p": .5, "y": 1}])
        self.assertEqual(result["coverage"], 0)
        self.assertIsNone(result["selective_error"])

    def test_negative_threshold_boundary_is_included(self):
        result = calibrate([{"p": .2, "y": 0}, {"p": .8, "y": 1}], threshold=.8)
        self.assertEqual(result["coverage"], 1)

    def test_calibration_invalid_data(self):
        for rows in ([], [{"p": 1.1, "y": 0}], [{"p": .5, "y": 2}], [{"p": True, "y": 1}]):
            with self.assertRaises(ValueError):
                calibrate(rows)


class InstallTests(unittest.TestCase):
    def test_three_personal_targets(self):
        paths = installer.destinations("all", home=Path("/temporary-user"))
        self.assertEqual(set(str(p) for p in paths), {
            "/temporary-user/.agents/skills/research-duo",
            "/temporary-user/.claude/skills/research-duo",
            "/temporary-user/.gemini/config/skills/research-duo"})

    def test_project_shared_location_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = installer.destinations("all", project=tmp)
            self.assertEqual(len(paths), 2)

    def test_install_refuses_overwrite_and_retains_backup_outside_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / ".agents" / "skills" / "research-duo"
            installer.install(dest)
            self.assertTrue((dest / "SKILL.md").exists())
            (dest / "custom.txt").write_text("retain me")
            with self.assertRaises(ValueError):
                installer.install(dest)
            _, backup = installer.install(dest, replace=True)
            self.assertEqual((backup / "custom.txt").read_text(), "retain me")
            self.assertNotIn(dest.parent, backup.parents)
            self.assertFalse((dest / "custom.txt").exists())
            run = subprocess.run([sys.executable, str(dest / "scripts" / "decision_tools.py"),
                                  "voi", str(dest / "assets" / "voi-example.json")],
                                 cwd=tmp, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(run.stdout)["evpi"], 50)

    def test_symlink_and_source_overlap_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "link"
            dest.symlink_to(SKILL, target_is_directory=True)
            with self.assertRaises(ValueError):
                installer.install(dest, replace=True)
        for dest in (SKILL, SKILL.parent, SKILL / "nested"):
            with self.assertRaises(ValueError):
                installer.install(dest, replace=True)

    def test_failed_swap_restores_previous_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "platform" / "skills" / "research-duo"
            installer.install(dest)
            (dest / "custom.txt").write_text("retain me")
            original = Path.rename
            def fail_staging(path, target):
                if path.parent.name.startswith(".research-duo-stage-"):
                    raise OSError("simulated swap failure")
                return original(path, target)
            with patch.object(Path, "rename", fail_staging), self.assertRaises(OSError):
                installer.install(dest, replace=True)
            self.assertEqual((dest / "custom.txt").read_text(), "retain me")


class CLITests(unittest.TestCase):
    def test_all_commands_return_json(self):
        for command, filename in (("gate","gate"), ("rank","ranking"), ("voi","voi"),
                                  ("robust","robust"), ("audit","evidence-graph"), ("calibrate","calibration")):
            with self.subTest(command=command):
                run = subprocess.run([sys.executable, str(SKILL / "scripts" / "decision_tools.py"), command,
                                      str(SKILL / "assets" / (filename + "-example.json"))],
                                     capture_output=True, text=True, check=True)
                self.assertIsInstance(json.loads(run.stdout), dict)

    def test_invalid_input_exits_without_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            source.write_text('{"a":1,"a":2}')
            run = subprocess.run([sys.executable, str(SKILL / "scripts" / "decision_tools.py"), "gate", str(source)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, "")


if __name__ == "__main__":
    unittest.main()
