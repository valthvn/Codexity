"""Sanitized snapshots; no shared .git and no following repository symlinks."""
from __future__ import annotations
import difflib
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import subprocess
from core import Error, atomic_json, digest, git

DENY_DIRS = {".git", ".codex", ".agents", ".gemini", ".antigravity", "node_modules",
             ".venv", "venv", "__pycache__", ".next", "dist", "build", "coverage"}
DENY_NAMES = {"AGENTS.md", "GEMINI.md", "CLAUDE.md", ".npmrc", ".pypirc", ".netrc",
              "credentials", "credentials.json", "secrets.json", "settings.local.json"}
SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
                   "*credentials*", "*secret*.json", "*.keystore")

def denied(name):
    path = PurePosixPath(name)
    return (any(p in DENY_DIRS for p in path.parts) or path.name in DENY_NAMES
            or any(fnmatch.fnmatch(path.name.casefold(), pattern) for pattern in SECRET_PATTERNS))

def safe_relative(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
        raise Error(f"Unsafe repository path: {name!r}")
    return p

def no_symlink(path: Path, root: Path):
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            return False
        cursor = cursor.parent
    return True

def read_stream(stream, retain):
    checksum = hashlib.sha256()
    chunks = []
    size = 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        checksum.update(chunk)
        size += len(chunk)
        if retain and size <= 2 * 1024 * 1024:
            chunks.append(chunk)
        elif retain:
            chunks.clear()
            retain = False
    return checksum.hexdigest(), size, b"".join(chunks) if retain else None

def collect(repo: Path, destination: Path | None = None, base=None):
    if base is not None:
        base = git(repo, "rev-parse", "--verify", base + "^{commit}")
        names = git(repo, "ls-tree", "-r", "--name-only", "-z", base, binary=True).split(b"\0")
    else:
        names = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True).split(b"\0")
    files, total = {}, 0
    for raw in sorted(set(names)):
        if not raw:
            continue
        name = raw.decode("utf-8", "surrogateescape")
        safe_relative(name)
        path = repo / name
        if base is None and not path.exists() and not path.is_symlink():
            continue
        eligible = not denied(name)
        mode = ""
        if base is not None:
            entry = git(repo, "ls-tree", base, "--", name).split()
            mode = entry[0] if entry else ""
            if mode == "120000":
                data = git(repo, "show", base + ":" + name, binary=True)
                sha, size = digest(data), len(data)
                eligible, reason = False, "symlink"
            elif mode not in ("100644", "100755"):
                data = (entry[2] if len(entry) > 2 else "unsupported").encode()
                sha, size = digest(data), len(data)
                eligible, reason = False, "symlink-or-submodule"
            else:
                reason = "excluded" if not eligible else ""
                size = int(git(repo, "cat-file", "-s", entry[2]))
                if eligible and (size > 2 * 1024 * 1024 or total + size > 64 * 1024 * 1024):
                    eligible, reason = False, "size-limit"
                proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "blob", entry[2]], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    sha, size, data = read_stream(proc.stdout, eligible)
                finally:
                    proc.stdout.close()
                if proc.wait(timeout=30):
                    raise Error("Cannot read baseline Git blob")
        elif not no_symlink(path, repo):
            data = os.fsencode(os.readlink(path)) if path.is_symlink() else b"symlink-parent"
            sha, size = digest(data), len(data)
            eligible, reason = False, "symlink"
        elif not path.is_file():
            data = git(repo, "ls-files", "--stage", "--", name).encode()
            sha, size = digest(data), len(data)
            eligible, reason = False, "unsupported-entry"
        else:
            reason = "excluded" if not eligible else ""
            size = path.stat().st_size
            if eligible and (size > 2 * 1024 * 1024 or total + size > 64 * 1024 * 1024):
                eligible, reason = False, "size-limit"
            with path.open("rb") as stream:
                sha, size, data = read_stream(stream, eligible)
        if eligible and (data is None or total + size > 64 * 1024 * 1024):
            eligible, reason = False, "size-limit"
        executable = (base is not None and mode == "100755") or (base is None and reason != "symlink" and path.is_file() and os.access(path, os.X_OK))
        files[name] = {"sha256": sha, "size": size, "copied": eligible,
                       "reason": reason, "mode": "symlink" if reason == "symlink" else "executable" if executable else "regular"}
        if eligible:
            total += size
            if destination is not None:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    result = {"files": files, "sha256": digest(json.dumps(files, sort_keys=True).encode()), "base": base}
    if destination is not None:
        atomic_json(destination.parent / (destination.name + ".manifest.json"), result)
    return result

def changed(before, after, scope=None):
    names = set(before["files"]) | set(after["files"])
    return sorted(n for n in names if (scope is None or n in scope) and before["files"].get(n) != after["files"].get(n))

def create_diff(before, after, old_dir: Path, new_dir: Path, scope=None):
    parts, omissions = [], []
    for name in changed(before, after, scope):
        a, b = before["files"].get(name), after["files"].get(name)
        if (a and not a["copied"]) or (b and not b["copied"]):
            omissions.append(name)
            parts.append(f"Changed file withheld from reviewer: {name}\n")
            continue
        old = (old_dir / name).read_bytes() if a else b""
        new = (new_dir / name).read_bytes() if b else b""
        try:
            if b"\0" in old or b"\0" in new:
                raise UnicodeError()
            parts.extend(difflib.unified_diff(old.decode("utf-8").splitlines(True), new.decode("utf-8").splitlines(True),
                                             fromfile="a/" + name, tofile="b/" + name))
            if a and b and a["mode"] != b["mode"]:
                parts.append(f"Mode changed: {name}: {a['mode']} -> {b['mode']}\n")
        except UnicodeError:
            omissions.append(name)
            parts.append(f"Binary change (inspect file if supported): {name}\n")
    text = "".join(parts)
    if len(text.encode()) > 4 * 1024 * 1024:
        raise Error("Diff exceeds 4 MiB; narrow task scope")
    return text, omissions
