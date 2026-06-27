"""
Judge Python submissions via subprocess. Student MUST define::

    def solve(data: str) -> str:
        ...
"""

from __future__ import annotations

import ast
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _embedded_runner_py() -> str:
    return r"""
import json, sys


def load_solve(user_path):
    with open(user_path, "r", encoding="utf-8") as fh:
        code = fh.read()
    compiled = compile(code, user_path, "exec")
    ns = {}
    exec(compiled, ns)
    fn = ns.get("solve")
    if not callable(fn):
        raise RuntimeError("Нужно определить solve(data: str) -> str")
    return fn


def main():
    user_path = sys.argv[1]
    inputs_json = sys.argv[2]
    inputs = json.loads(inputs_json)
    solve = load_solve(user_path)
    results = []
    for inp in inputs:
        try:
            out = solve(inp)
            results.append({"ok": True, "out": "" if out is None else str(out), "exc": None})
        except Exception as exc:
            results.append({"ok": False, "out": "", "exc": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(results))


if __name__ == "__main__":
    main()
"""


def lint_python_syntax(source: str) -> str | None:
    try:
        ast.parse(source)
        return None
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"


def run_python_tests(
    source_code: str,
    cases: list[dict],
    *,
    timeout_sec: float,
) -> tuple[str, dict]:
    """
    cases entries: stdin_data, expected_stdout, is_public (bool).

    Returns (short_verdict, full_json_safe_dict).
    """
    lint_err = lint_python_syntax(source_code)
    if lint_err:
        return "CE", {"verdict": "CE", "message": lint_err, "cases_public": [], "hidden": {}}

    stdin_list = [str(c["stdin_data"]) for c in cases]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(source_code)
        user_path = tmp.name

    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_runner.py", delete=False, encoding="utf-8"
    ) as rtmp:
        rtmp.write(_embedded_runner_py())
        runner_path = rtmp.name

    try:
        proc = subprocess.run(
            ["python", runner_path, user_path, json.dumps(stdin_list)],
            capture_output=True,
            text=True,
            timeout=max(timeout_sec, 2),
        )
        if proc.returncode != 0:
            tail = proc.stderr.strip() or proc.stdout.strip() or ""
            return "RE", {
                "verdict": "RE",
                "message": tail[:2048],
                "cases_public": [],
                "hidden": {},
            }
        results = json.loads(proc.stdout.strip())
    except subprocess.TimeoutExpired:
        return "TLE", {
            "verdict": "TLE",
            "message": "Time limit exceeded",
            "cases_public": [],
            "hidden": {},
        }
    except Exception as exc:
        logger.exception("judge fatal")
        return "IE", {
            "verdict": "IE",
            "message": str(exc),
            "cases_public": [],
            "hidden": {},
        }
    finally:
        Path(user_path).unlink(missing_ok=True)
        Path(runner_path).unlink(missing_ok=True)

    pub_detail: list[dict] = []
    pub_pass = pub_total = 0
    hid_pass = hid_total = 0
    hid_fail_msg: str | None = None

    for i, case in enumerate(cases):
        r = results[i] if i < len(results) else {"ok": False, "exc": "no-result"}
        is_pub = bool(case.get("is_public"))
        expected = str(case.get("expected_stdout", "")).strip()
        if r.get("exc"):
            ok = False
            got = ""
            err = str(r["exc"])
        elif r.get("ok"):
            got = str(r.get("out", "")).strip()
            ok = got == expected
            err = None
        else:
            ok = False
            got = ""
            err = "solve failed"

        if is_pub:
            pub_total += 1
            if ok:
                pub_pass += 1
            pub_detail.append(
                {
                    "passed": ok,
                    "expected": expected,
                    "got": got,
                    "error": err,
                }
            )
        else:
            hid_total += 1
            if ok:
                hid_pass += 1
            elif hid_fail_msg is None and err:
                hid_fail_msg = err[:512]
            elif hid_fail_msg is None and not ok:
                hid_fail_msg = "wrong answer"

    pub_ok_all = pub_total == pub_pass if pub_total else True
    hid_ok_all = hid_total == hid_pass if hid_total else True
    all_ok = pub_ok_all and hid_ok_all

    hidden_block = {"passed": hid_pass, "total": hid_total}

    if all_ok:
        return "AC", {
            "verdict": "AC",
            "message": "Accepted",
            "cases_public": pub_detail,
            "hidden": hidden_block,
        }

    verdict = "WA"
    if pub_pass < pub_total:
        verdict = "WA"
    elif hid_total > 0 and hid_pass < hid_total:
        verdict = "WA"

    return verdict, {
        "verdict": verdict,
        "message": hid_fail_msg or "Неверный ответ на один или несколько тестов",
        "cases_public": pub_detail,
        "hidden": hidden_block,
    }
