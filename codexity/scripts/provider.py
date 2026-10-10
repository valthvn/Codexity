"""Antigravity headless adapter: pinned model, explicit conversations, strict JSON."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
from core import Error, execute, read_json
from snapshot import safe_relative

DEFAULTS = {"command": ["agy"], "model": "gemini-3.8-flash-high", "effort": "high", "timeout": 600}
REQUIRED_FLAGS = ("--input-format", "--output-format", "--json-schema", "--model", "--effort", "--conversation", "--sandbox")

def config(path=None):
    result = dict(DEFAULTS)
    if path:
        user = read_json(Path(path))
        if set(user) - set(DEFAULTS):
            raise Error("Unknown provider configuration keys")
        result.update(user)
    cmd = result["command"]
    if not isinstance(cmd, list) or not cmd or any(not isinstance(v, str) or not v or "\0" in v for v in cmd):
        raise Error("Provider command must be an argv array")
    # Only executable + optional interpreter entrypoint; never inject permission flags.
    if any(v.startswith("-") for v in cmd[1:]):
        raise Error("Provider command may contain an executable and entrypoint, not CLI flags")
    found = shutil.which(cmd[0])
    if not found:
        raise Error("Antigravity executable not found. Install/authenticate agy locally, then run doctor.")
    if Path(found).suffix.lower() in (".cmd", ".bat"):
        raise Error("agy resolves to a batch wrapper. Configure node.exe plus the verified CLI .js entrypoint.")
    result["command"] = [str(Path(found).resolve()), *cmd[1:]]
    if len(cmd) > 1:
        entry = Path(cmd[1]).expanduser().resolve()
        if len(cmd) != 2 or not entry.is_file():
            raise Error("Provider interpreter command requires one existing absolute entrypoint")
        result["command"][1] = str(entry)
    if not isinstance(result["model"], str) or not result["model"]:
        raise Error("Pin an explicit model from agy models")
    if result["effort"] not in ("low", "medium", "high"):
        raise Error("Invalid reasoning effort")
    if type(result["timeout"]) is not int or not 1 <= result["timeout"] <= 1800:
        raise Error("Timeout must be 1..1800 seconds")
    return result

def environment():
    allowed = {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR",
               "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "SSL_CERT_FILE"}
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}

def doctor(repo: Path, cfg):
    help_result = execute([*cfg["command"], "--help"], repo, timeout=20, env=environment())
    help_text = help_result["stdout"] + help_result["stderr"]
    missing = [f for f in REQUIRED_FLAGS if f not in help_text]
    models = execute([*cfg["command"], "models"], repo, timeout=30, env=environment())
    model_found = cfg["model"] in models["stdout"]
    return {"ready": help_result["returncode"] == 0 and not missing and models["returncode"] == 0 and model_found,
            "missing_flags": missing, "model_available": model_found, "model": cfg["model"],
            "authentication": "Not proven by listing models; first successful review confirms cached login.",
            "note": "No permission bypass or API key. Native Windows launcher or node entrypoint required."}

def schema(snapshot_sha, plan_sha):
    text = {"type": "string", "minLength": 1}
    finding = {"type": "object", "additionalProperties": False, "properties": {
        "title": text, "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "path": {"type": "string"}, "line": {"type": ["integer", "null"], "minimum": 1},
        "evidence": text, "reproduction": text, "suggestion": text}}
    finding["required"] = list(finding["properties"])
    props = {"verdict": {"type": "string", "enum": ["APPROVED", "REVISE", "BLOCKED"]},
             "snapshot_sha256": {"type": "string", "const": snapshot_sha},
             "plan_sha256": {"const": plan_sha},
             "evidence_tier": {"type": "string", "enum": ["FULL", "DEGRADED", "UNVERIFIED"]},
             "summary": text, "findings": {"type": "array", "items": finding, "maxItems": 100},
             "coverage": {"type": "array", "items": text, "minItems": 1, "maxItems": 100},
             "limitations": {"type": "array", "items": text, "maxItems": 100}}
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}

def validate_report(report, snapshot_sha, plan_sha, known_paths):
    expected = schema(snapshot_sha, plan_sha)["required"]
    if not isinstance(report, dict) or set(report) != set(expected):
        raise Error("Malformed review: missing or extra fields")
    if report["snapshot_sha256"] != snapshot_sha or report["plan_sha256"] != plan_sha:
        raise Error("Review hashes do not match the submitted artifacts")
    if report["verdict"] not in ("APPROVED", "REVISE", "BLOCKED") or report["evidence_tier"] not in ("FULL", "DEGRADED", "UNVERIFIED"):
        raise Error("Invalid review verdict/evidence tier")
    if not isinstance(report["summary"], str) or not report["summary"].strip():
        raise Error("Review needs a summary")
    for key in ("coverage", "limitations"):
        value = report[key]
        if not isinstance(value, list) or len(value) > 100 or any(not isinstance(x, str) or not x.strip() for x in value):
            raise Error("Invalid review " + key)
    if not report["coverage"]:
        raise Error("Review has no coverage evidence")
    findings = report["findings"]
    if not isinstance(findings, list) or len(findings) > 100:
        raise Error("Invalid findings array")
    for f in findings:
        if not isinstance(f, dict) or set(f) != {"title", "severity", "path", "line", "evidence", "reproduction", "suggestion"}:
            raise Error("Malformed finding")
        if f["severity"] not in ("HIGH", "MEDIUM", "LOW"):
            raise Error("Invalid finding severity")
        if any(not isinstance(f[k], str) or not f[k].strip() for k in ("title", "evidence", "reproduction", "suggestion")):
            raise Error("Finding lacks evidence or reproduction")
        if not isinstance(f["path"], str):
            raise Error("Invalid finding path")
        if f["path"]:
            safe_relative(f["path"])
            if f["path"] not in known_paths and f["path"] != "PLAN.md":
                raise Error("Finding cites a nonexistent snapshot path")
        if f["line"] is not None and (type(f["line"]) is not int or f["line"] < 1):
            raise Error("Invalid finding line")
    if report["verdict"] == "APPROVED" and any(f["severity"] != "LOW" for f in findings):
        raise Error("Contradictory approval contains blocking findings")
    return report

def review(workspace: Path, cfg, prompt, expected_schema, cancel, conversation=None):
    argv = [*cfg["command"], "--input-format", "stream-json", "--output-format", "stream-json",
            "--json-schema", str(workspace / "review.schema.json"), "--model", cfg["model"],
            "--effort", cfg["effort"], "--sandbox"]
    if conversation:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", conversation):
            raise Error("Invalid persisted conversation identity")
        argv += ["--conversation", conversation]
    (workspace / "review.schema.json").write_text(json.dumps(expected_schema), encoding="utf-8")
    message = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
    result = execute(argv, workspace, cfg["timeout"], cancel, environment(), message)
    if result["returncode"] or result["stdout_truncated"] or result["stderr_truncated"]:
        raise Error(f"Provider failed (exit {result['returncode']}) or exceeded output limits; no approval recorded")
    terminal = []
    try:
        for line in result["stdout"].splitlines():
            item = json.loads(line)
            if item.get("event") == "result":
                terminal.append(item["result"])
    except (ValueError, TypeError, KeyError) as exc:
        raise Error("Invalid Antigravity event stream") from exc
    if len(terminal) != 1 or terminal[0].get("status") != "SUCCESS":
        raise Error("Antigravity did not return exactly one successful result")
    envelope = terminal[0]
    session = envelope.get("conversation_id")
    if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session):
        raise Error("Provider returned an invalid conversation ID")
    if conversation and session != conversation:
        raise Error("Provider resumed the wrong conversation")
    report = envelope.get("structured_output")
    if report is None:
        try:
            report = json.loads(envelope.get("response", ""))
        except ValueError as exc:
            raise Error("Missing structured JSON review") from exc
    # Soft-denied tools can coexist with SUCCESS; they must degrade evidence.
    notices = result["stderr"].casefold()
    degraded = any(w in notices for w in ("denied", "permission", "not allowed", "cannot access", "unauthenticated"))
    return report, session, degraded, envelope.get("usage", {})
