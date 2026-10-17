#!/usr/bin/env python3
"""Optional, bounded TypeSafe text client. Dry-run unless --execute is passed."""
import argparse
import datetime as dt
import email.utils
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MAX_BYTES = 2 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, low=0, high=1):
    require(type(value) in (int, float) and math.isfinite(value), f"{name}: finite number required")
    require(low <= value <= high, f"{name}: outside [{low}, {high}]")
    return value


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"{name}: nonempty string required")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_constant)


def encode(value):
    # Preserve option order: it is part of the evaluated request.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def load_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input exceeds local 2 MiB limit")
    return decode(raw)


def validate_request(request):
    require(isinstance(request, dict), "request must be an object")
    require(set(request) == {"model", "state", "questions"}, "request requires only model, state, questions")
    text(request["model"], "model")
    require(isinstance(request["state"], (str, dict, list)), "state must be text, object or array")
    questions = request["questions"]
    require(isinstance(questions, dict) and questions, "questions must be a nonempty object")
    for key, q in questions.items():
        text(key, "question id")
        require(isinstance(q, dict), f"{key}: question must be an object")
        require(set(q) <= {"type", "instructions", "criteria"}, f"{key}: unsupported question field")
        require(q.get("type") in ("choice", "score", "noul"), f"{key}: unsupported type")
        require(isinstance(q.get("instructions"), (str, dict, list)) and q["instructions"], f"{key}: instructions required")
        criteria = q.get("criteria")
        if q["type"] == "choice":
            require(isinstance(criteria, dict) and 2 <= len(criteria) <= 255, f"{key}: need 2–255 choices")
            for option, description in criteria.items():
                text(option, "option")
                require(description is None or isinstance(description, (str, dict, list)), "invalid choice description")
        elif q["type"] == "score":
            require(isinstance(criteria, list) and 2 <= len(criteria) <= 10, f"{key}: need 2–10 ordered levels")
            require(all(isinstance(v, (str, dict, list)) for v in criteria), "invalid score level")
        elif criteria is not None:
            require(isinstance(criteria, dict) and set(criteria) <= {"true", "false"}, "invalid noul criteria")
            require(all(isinstance(v, (str, dict, list)) for v in criteria.values()), "invalid noul description")
    require(len(encode(request)) <= MAX_BYTES, "request exceeds local 2 MiB limit")


def distribution(values, keys):
    require(isinstance(values, dict) and set(values) == set(keys), "probability options do not match question")
    for key, value in values.items():
        number(value, f"probability {key}")
    require(math.isclose(sum(values.values()), 1, abs_tol=0.001), "probabilities must sum to one")


def validate_answer(question, answer):
    require(isinstance(answer, dict) and answer.get("type") == question["type"], "answer type mismatch")
    kind = question["type"]
    if kind == "noul":
        number(answer.get("noul"), "noul")
        require("confidence" not in answer, "Noul has no provider confidence field")
        return
    keys = list(question["criteria"]) if kind == "choice" else [str(i) for i in range(len(question["criteria"]))]
    probs = answer.get("probabilities")
    distribution(probs, keys)
    number(answer.get("confidence"), "confidence")
    if kind == "choice":
        selected = answer.get("choice")
        require(isinstance(selected, str) and selected in probs, "choice outside allowed options")
        require(probs[selected] >= max(probs.values()) - 1e-8, "choice is not a probability maximum")
        expected = (max(probs.values()) - 1 / len(probs)) / (1 - 1 / len(probs))
        require(abs(answer["confidence"] - expected) <= 0.02, "Choice confidence inconsistent with distribution")
    else:
        score = number(answer.get("score"), "score", 0, len(keys) - 1)
        expected = sum(int(k) * probs[k] for k in keys)
        require(abs(score - expected) <= 0.02, "score inconsistent with distribution")
        require(isinstance(answer.get("legend"), dict) and set(answer["legend"]) == set(keys), "score legend mismatch")


def validate_response(request, response):
    require(isinstance(response, dict), "response must be an object")
    text(response.get("model"), "response model")
    answers = response.get("answers")
    require(isinstance(answers, dict) and set(answers) == set(request["questions"]), "missing or unexpected answers")
    for key, question in request["questions"].items():
        validate_answer(question, answers[key])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward an Authorization header to another URL.


def retry_delay(header, attempt):
    if header is None:
        return min(2 ** attempt, 10)
    try:
        delay = float(header)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(header)
            delay = (when - dt.datetime.now(dt.timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            raise RuntimeError("unreadable Retry-After; retry later") from None
    if not math.isfinite(delay) or delay > 10:
        raise RuntimeError("service requested a longer wait; retry later")
    return max(0, delay)


def call_api(request, api_key, opener=None, sleep=time.sleep):
    validate_request(request)
    require(isinstance(api_key, str) and bool(api_key.strip()), "TYPESAFE_API_KEY is missing")
    opener = opener or urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(ENDPOINT, data=encode(request), headers={
        "Authorization": "Bearer " + api_key, "Content-Type": "application/json"
    }, method="POST")
    for attempt in range(3):
        try:
            with opener.open(req, timeout=45) as handle:
                raw = handle.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "response exceeds local limit")
            response = decode(raw)
            validate_response(request, response)
            return response
        except urllib.error.HTTPError as error:
            status = error.code
            retry_after = error.headers.get("Retry-After") if error.headers else None
            error.close()
            if status not in (429, 500, 502, 503, 504, 529) or attempt == 2:
                raise RuntimeError(f"TypeSafe HTTP {status}; no result produced") from None
            sleep(retry_delay(retry_after, attempt))
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("TypeSafe network failure; no result produced") from None
    raise RuntimeError("retry budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", help="New result file; existing files are not overwritten")
    args = parser.parse_args()
    try:
        if args.out:
            require(not Path(args.out).exists(), "output already exists")
        request = load_json(args.request)
        validate_request(request)
        record = {"provider": "jev" if args.execute else "dry_run", "executed": args.execute,
                  "requested_model": request["model"], "question_count": len(request["questions"]),
                  "request_sha256": hashlib.sha256(encode(request)).hexdigest(),
                  "questions_sha256": hashlib.sha256(encode(request["questions"])).hexdigest(),
                  "calibration_status": "unvalidated"}
        if args.execute:
            record["response"] = call_api(request, os.environ.get("TYPESAFE_API_KEY"))
            record["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        result = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.out:
            with Path(args.out).open("x", encoding="utf-8") as handle:
                handle.write(result)
            print(f"Saved {args.out}; executed={args.execute}")
        else:
            print(result, end="")
        return 0
    except (ValueError, RuntimeError, OSError, RecursionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
