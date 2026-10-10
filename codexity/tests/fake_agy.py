#!/usr/bin/env python3
"""Offline test double; never use this executable to approve a real project."""
import json
from pathlib import Path
import sys
import time
import uuid

here = Path(__file__).resolve().parent
args = sys.argv[1:]
if args == ["--help"]:
    print("--input-format --output-format --json-schema --model --effort --conversation --sandbox")
    sys.exit(0)
if args == ["models"]:
    print("gemini-3.8-flash-high")
    sys.exit(0)
scenario = json.loads((here / "scenario.json").read_text())
event = json.loads(sys.stdin.readline())
schema = json.loads(Path(args[args.index("--json-schema") + 1]).read_text())
context = json.loads(Path("context.json").read_text())
capture = {"args": args, "prompt": event["message"]["content"], "context": context,
           "files": sorted(str(p.relative_to(Path.cwd())) for p in Path.cwd().rglob("*") if p.is_file()),
           "diff": Path("diff.patch").read_text()}
(here / "capture.json").write_text(json.dumps(capture))
case = scenario.get("case", "approve")
if case == "timeout":
    time.sleep(5)
if case == "error":
    print("provider failed", file=sys.stderr)
    sys.exit(1)
if case == "invalid-json":
    print("not JSON")
    sys.exit(0)
if case == "soft-deny":
    print("tool command denied by permission policy", file=sys.stderr)
if case == "mutate":
    Path("repo/app.py").write_text("reviewer accidentally edited this\n")
report = {"verdict": "APPROVED", "snapshot_sha256": schema["properties"]["snapshot_sha256"]["const"],
          "plan_sha256": schema["properties"]["plan_sha256"]["const"], "evidence_tier": "FULL",
          "summary": "Source inspected", "findings": [], "coverage": ["app.py and its callers"], "limitations": []}
if case in ("finding", "contradiction", "low"):
    report["findings"] = [{"title": "Incorrect result for zero", "severity": "LOW" if case == "low" else "HIGH",
        "path": "app.py", "line": 1, "evidence": "app.py returns 1 for input zero",
        "reproduction": "Call value(0); expect 0", "suggestion": "Return the correct result"}]
    if case == "finding":
        report["verdict"] = "REVISE"
if case == "wrong-hash":
    report["snapshot_sha256"] = "0" * 64
if case == "malformed":
    report.pop("coverage")
if case == "path-traversal":
    report["findings"] = [{"title": "Bad path", "severity": "LOW", "path": "../outside", "line": 1,
                            "evidence": "e", "reproduction": "r", "suggestion": "s"}]
session = args[args.index("--conversation") + 1] if "--conversation" in args else scenario.get("session", uuid.uuid4().hex)
if case == "wrong-session":
    session = "different-session"
envelope = {"conversation_id": session, "status": "SUCCESS", "structured_output": report,
            "usage": {"input_tokens": 100, "output_tokens": 50}}
if case == "bad-status":
    envelope["status"] = "WAITING"
if case == "response-json":
    envelope.pop("structured_output")
    envelope["response"] = json.dumps(report)
print(json.dumps({"event": "init", "conversation_id": session}))
print(json.dumps({"event": "result", "result": envelope}))
