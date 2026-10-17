import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-duo"
sys.path.insert(0, str(SKILL / "scripts"))
from jev_client import (call_api, decode, encode, load_json, retry_delay,
                        validate_answer, validate_request, validate_response)
from decision_tools import calibrate, gate, rank


def asset(name):
    return load_json(SKILL / "assets" / name)


def response():
    return {"model": "jev-test-version", "answers": {
        "citation_relation": {"type": "choice", "choice": "insufficient", "probabilities": {
            "supports": 0.02, "insufficient": 0.96, "contradicts": 0.02}, "confidence": 0.94},
        "confounding_present": {"type": "noul", "noul": 0.98},
        "design_strength": {"type": "score", "score": 0.1, "probabilities": {
            "0": 0.9, "1": 0.1, "2": 0.0}, "confidence": 0.85,
            "legend": {"0": "confounded", "1": "partial", "2": "controlled"}}
    }}


def validated_context():
    data = asset("gate-example.json")
    data.update(evidence_status="verified", provider="jev", model="jev-test-version")
    data["calibration"] = {"validated": True, "model": data["model"],
                           "question_set_id": data["question_set_id"], "validation_ref": "SYNTHETIC-TEST-ONLY"}
    return data


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.request = asset("jev-request.json")

    def test_valid_three_primitives(self):
        validate_request(self.request)
        validate_response(self.request, response())

    def test_reject_nonfinite_json(self):
        for raw in ('{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}'):
            with self.assertRaises(ValueError):
                decode(raw)

    def test_reject_duplicate_keys(self):
        with self.assertRaises(ValueError):
            decode('{"x":1,"x":2}')

    def test_reject_unsupported_type(self):
        self.request["questions"]["citation_relation"]["type"] = "free_text"
        with self.assertRaises(ValueError):
            validate_request(self.request)

    def test_require_full_instructions(self):
        del self.request["questions"]["citation_relation"]["instructions"]
        with self.assertRaises(ValueError):
            validate_request(self.request)

    def test_score_levels_bounded(self):
        self.request["questions"]["design_strength"]["criteria"] = ["one"]
        with self.assertRaises(ValueError):
            validate_request(self.request)

    def test_missing_answer_is_failure(self):
        data = response()
        del data["answers"]["confounding_present"]
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_outside_choice_rejected(self):
        data = response()
        data["answers"]["citation_relation"]["choice"] = "not_allowed"
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_probability_mass_checked(self):
        data = response()
        data["answers"]["citation_relation"]["probabilities"]["supports"] = 0.5
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_choice_must_be_argmax(self):
        data = response()
        data["answers"]["citation_relation"]["choice"] = "supports"
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_confidence_is_not_arbitrary(self):
        data = response()
        data["answers"]["citation_relation"]["confidence"] = 0.2
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_score_expectation_checked(self):
        data = response()
        data["answers"]["design_strength"]["score"] = 1.8
        with self.assertRaises(ValueError):
            validate_response(self.request, data)

    def test_noul_does_not_accept_bool_or_confidence(self):
        for answer in ({"type": "noul", "noul": True}, {"type": "noul", "noul": 0.8, "confidence": 0.6}):
            with self.assertRaises(ValueError):
                validate_answer({"type": "noul"}, answer)

    def test_option_order_retained(self):
        self.assertEqual(encode({"b": 1, "a": 2}), b'{"b":1,"a":2}')


class TransportTests(unittest.TestCase):
    def handle(self):
        return io.BytesIO(encode(response()))

    def test_mock_success_and_endpoint(self):
        opener = Mock()
        opener.open.return_value = self.handle()
        result = call_api(asset("jev-request.json"), "test-only-key", opener)
        self.assertEqual(result["model"], "jev-test-version")
        self.assertEqual(opener.open.call_args.args[0].full_url, "https://api.typesafe.ai/v1/systemone")

    def test_missing_key_no_network(self):
        opener = Mock()
        with self.assertRaises(ValueError):
            call_api(asset("jev-request.json"), None, opener)
        opener.open.assert_not_called()

    def test_401_no_retry_no_body_leak(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://api.typesafe.ai", 401, "secret", {}, io.BytesIO(b"private-data"))
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
            call_api(asset("jev-request.json"), "test-only-key", opener)
        self.assertNotIn("private-data", str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_429_retry_then_success(self):
        opener, sleep = Mock(), Mock()
        opener.open.side_effect = [urllib.error.HTTPError("https://api.typesafe.ai", 429, "rate", {"Retry-After": "1"}, None), self.handle()]
        call_api(asset("jev-request.json"), "test-only-key", opener, sleep)
        sleep.assert_called_once_with(1.0)
        self.assertEqual(opener.open.call_count, 2)

    def test_retry_budget(self):
        opener, sleep = Mock(), Mock()
        opener.open.side_effect = [urllib.error.HTTPError("https://api.typesafe.ai", 529, "busy", {}, None) for _ in range(3)]
        with self.assertRaisesRegex(RuntimeError, "529"):
            call_api(asset("jev-request.json"), "test-only-key", opener, sleep)
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_no_early_retry_when_long_wait_requested(self):
        with self.assertRaises(RuntimeError):
            retry_delay("60", 0)

    def test_network_error_redacted(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("secret-containing-error")
        with self.assertRaises(RuntimeError) as caught:
            call_api(asset("jev-request.json"), "test-only-key", opener)
        self.assertNotIn("secret-containing-error", str(caught.exception))

    def test_dry_run_cli(self):
        run = subprocess.run([sys.executable, str(SKILL / "scripts" / "jev_client.py"), str(SKILL / "assets" / "jev-request.json")], capture_output=True, text=True, check=True)
        result = json.loads(run.stdout)
        self.assertFalse(result["executed"])
        self.assertNotIn("response", result)
        self.assertNotIn("state", result)


class GateTests(unittest.TestCase):
    def test_conflicting_evidence_beats_high_probability(self):
        result = gate(asset("gate-example.json"))
        self.assertEqual(result["route"], "deliberate")
        self.assertFalse(result["execute"])

    def test_validated_low_risk_is_advisory(self):
        result = gate(validated_context())
        self.assertEqual(result["route"], "recommend")
        self.assertFalse(result["execute"])

    def test_missing_evidence_gathered(self):
        for state in ("missing", "partial"):
            data = validated_context()
            data["evidence_status"] = state
            self.assertEqual(gate(data)["route"], "gather_evidence")

    def test_high_risk_and_irreversibility_reviewed(self):
        for update in ({"risk": "high"}, {"reversible": False}):
            data = validated_context()
            data.update(update)
            self.assertEqual(gate(data)["route"], "review")

    def test_mismatched_or_unvalidated_never_recommended(self):
        for update in ({"validated": False}, {"model": "wrong-version"}, {"question_set_id": "wrong-questions"}, {"validation_ref": ""}):
            data = validated_context()
            data["calibration"].update(update)
            self.assertEqual(gate(data)["route"], "review")

    def test_fallback_and_ood_reviewed(self):
        for update in ({"provider": "llm"}, {"provider": "fixture"}, {"in_distribution": False}, {"model": "jev-latest"}):
            data = validated_context()
            data.update(update)
            self.assertEqual(gate(data)["route"], "review")

    def test_explicit_abstention(self):
        data = validated_context()
        data["abstain_options"] = ["supports", "insufficient"]
        self.assertEqual(gate(data)["reason"], "explicit_abstention")

    def test_near_tie_not_recommended(self):
        data = validated_context()
        data["answer"].update(probabilities={"supports": .51, "insufficient": .48, "contradicts": .01}, confidence=.265)
        self.assertEqual(gate(data)["route"], "deliberate")

    def test_invalid_context_fails_closed(self):
        for update in ({"risk": "unknown"}, {"reversible": "false"}, {"evidence_status": "probably"}):
            data = validated_context()
            data.update(update)
            with self.assertRaises(ValueError):
                gate(data)


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
    def test_install_refuses_overwrite_and_retains_backup(self):
        spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts" / "install_skill.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "research-duo"
            module.install(dest)
            self.assertTrue((dest / "SKILL.md").exists())
            (dest / "custom.txt").write_text("retain me")
            with self.assertRaises(ValueError):
                module.install(dest)
            _, backup = module.install(dest, replace=True)
            self.assertEqual((backup / "custom.txt").read_text(), "retain me")
            self.assertFalse((dest / "custom.txt").exists())


if __name__ == "__main__":
    unittest.main()
