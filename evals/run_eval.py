#!/usr/bin/env python3
"""Run the fit-or-skip eval set against the live endpoint.

Reads evals/cases.json (8 hand-written cases), POSTs each one to the
/evaluate endpoint, and scores them on the key field (fit_verdict).

Retry policy (mirrors src/llm/model.py):
  - Retry ONLY transient failures: timeouts, HTTP 429, HTTP 5xx.
  - Never retry 400/401/403 (a bad payload/key stays bad).
  - Exponential backoff with jitter: ~1s, ~2s, ~4s (+ small random amount).
  - If a 429 carries a Retry-After header, obey it instead of guessing.

Usage (from the repo root):
    python evals/run_eval.py [--endpoint http://127.0.0.1:8000/evaluate]
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "evals" / "cases.json"
RESULTS_FILE = ROOT / "evals" / "results.jsonl"
MAX_ATTEMPTS = 3


def get_prompt_version():
    try:
        sys.path.insert(0, str(ROOT))
        from src.llm.prompt import get_latest_prompt_info  # noqa: PLC0415

        return get_latest_prompt_info()[1]
    except Exception:
        return "unknown"


def post_with_retry(endpoint: str, payload: dict) -> dict:
    """POST payload to endpoint with the documented retry policy."""
    data = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(MAX_ATTEMPTS):
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (400, 401, 403):
                raise RuntimeError(
                    f"HTTP {exc.code} (permanent, not retried): {body}"
                ) from exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = 1.0
                else:
                    delay = 2 ** attempt + random.uniform(0, 0.5)
                print(f"    ! HTTP 429 (attempt {attempt + 1}), waiting {delay:.1f}s")
                time.sleep(delay)
                last_error = exc
                continue
            if 500 <= exc.code < 600:
                delay = 2 ** attempt + random.uniform(0, 0.5)
                print(f"    ! HTTP {exc.code} (attempt {attempt + 1}), waiting {delay:.1f}s")
                time.sleep(delay)
                last_error = exc
                continue
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            delay = 2 ** attempt + random.uniform(0, 0.5)
            print(f"    ! connection/timeout (attempt {attempt + 1}), waiting {delay:.1f}s")
            time.sleep(delay)
            last_error = exc
            continue

    raise RuntimeError(f"Endpoint unreachable after {MAX_ATTEMPTS} attempts: {last_error}")


def check_expected(actual: dict, expected: dict) -> list:
    """Return a list of strict-check violations (empty means fully correct)."""
    violations = []
    key = expected.get("fit_verdict")
    if actual.get("fit_verdict") != key:
        violations.append(f"fit_verdict: expected {key!r}, got {actual.get('fit_verdict')!r}")
    db = expected.get("primary_dealbreaker")
    if db and actual.get("primary_dealbreaker") != db:
        violations.append(
            f"primary_dealbreaker: expected {db!r}, got {actual.get('primary_dealbreaker')!r}"
        )
    if expected.get("missing_requirements") is not None:
        exp_reqs = sorted(expected["missing_requirements"])
        act_reqs = sorted(actual.get("missing_requirements") or [])
        if exp_reqs != act_reqs:
            violations.append(f"missing_requirements: expected {exp_reqs}, got {act_reqs}")
    conf = actual.get("confidence")
    if "confidence_min" in expected and (conf is None or conf < expected["confidence_min"]):
        violations.append(
            f"confidence: expected >= {expected['confidence_min']}, got {conf}"
        )
    if "confidence_max" in expected and (conf is None or conf > expected["confidence_max"]):
        violations.append(
            f"confidence: expected < {expected['confidence_max']}, got {conf}"
        )
    return violations


def main():
    parser = argparse.ArgumentParser(description="Run the fit-or-skip eval set.")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8000/evaluate",
        help="URL of the /evaluate endpoint (default: local FastAPI).",
    )
    args = parser.parse_args()

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    key_field = cases.get("key_field", "fit_verdict")
    case_list = cases["cases"]
    prompt_version = get_prompt_version()
    now = datetime.now(timezone.utc).isoformat()

    print(f"Eval run: {now}")
    print(f"Prompt version: {prompt_version}")
    print(f"Endpoint: {args.endpoint}")
    print(f"Cases: {len(case_list)} | Key field: {key_field}")
    print("-" * 72)

    results = []
    for case in case_list:
        cid = case["id"]
        try:
            actual = post_with_retry(args.endpoint, case["input"])
            violations = check_expected(actual, case["expected"])
        except Exception as exc:  # noqa: BLE001 - a failed case is a failed case
            actual = {"error": str(exc)}
            violations = [f"request failed: {exc}"]

        key_ok = actual.get(key_field) == case["expected"].get(key_field)
        strict_ok = not violations
        results.append(
            {
                "id": cid,
                "actual": actual,
                "expected": case["expected"],
                "key_ok": key_ok,
                "strict_ok": strict_ok,
                "violations": violations,
            }
        )
        status = "PASS" if key_ok else "FAIL"
        print(f"  [{status}] {cid}: {actual.get(key_field, actual)}")

    print("-" * 72)
    key_score = sum(1 for r in results if r["key_ok"])
    strict_score = sum(1 for r in results if r["strict_ok"])
    total = len(results)

    print(f"Score on key field '{key_field}': {key_score}/{total} ({key_score / total:.0%})")
    print(f"Strict (verdict + dealbreaker + confidence + missing_requirements): "
          f"{strict_score}/{total} ({strict_score / total:.0%})")

    failures = [r for r in results if not r["key_ok"]]
    if failures:
        print("\nFailures (key field):")
        for r in failures:
            print(f"  - {r['id']}: expected {r['expected'].get(key_field)!r}, "
                  f"got {r['actual'].get(key_field)!r}")
    else:
        print("\nFailures (key field): none")

    strict_warnings = [r for r in results if r["key_ok"] and not r["strict_ok"]]
    if strict_warnings:
        print("\nWarnings (key field passed, strict checks failed):")
        for r in strict_warnings:
            print(f"  - {r['id']}: {'; '.join(r['violations'])}")

    # Append a run record for history.
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": now,
        "prompt_version": prompt_version,
        "endpoint": args.endpoint,
        "total": total,
        "key_score": key_score,
        "key_field": key_field,
        "strict_score": strict_score,
        "failed_ids": [r["id"] for r in failures],
    }
    with RESULTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"\nRun record appended to {RESULTS_FILE.name}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
