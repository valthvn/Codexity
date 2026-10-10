"""Durable state, portable locks and bounded subprocesses (standard library)."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

class Error(RuntimeError):
    pass

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Error(f"Cannot read {path.name}: {exc}") from exc

def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

@contextlib.contextmanager
def lock(directory: Path):
    """OS advisory locks release on process exit, without probing/killing any PID."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "lock.json"
    owner = {"pid": os.getpid(), "host": socket.gethostname(), "token": os.urandom(16).hex()}
    # Keep the locked inode: deleting a lock file can let two processes lock
    # different inodes under the same name. lock.json is diagnostic only.
    with (directory / "lock.bin").open("a+b") as guard:
        guard.seek(0, os.SEEK_END)
        if guard.tell() == 0:
            guard.write(b"\0")
            guard.flush()
        guard.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Error("Another Codexity command owns this lock")
        try:
            atomic_json(path, owner)
            yield
        finally:
            try:
                if path.exists() and read_json(path).get("token") == owner["token"]:
                    path.unlink()
            finally:
                guard.seek(0)
                if os.name == "nt":
                    msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(guard.fileno(), fcntl.LOCK_UN)

def git(repo: Path, *args, binary=False):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)
    if p.returncode:
        raise Error("Git command failed: " + p.stderr.decode("utf-8", "replace")[:500])
    return p.stdout if binary else p.stdout.decode("utf-8", "surrogateescape").strip()

def repo_root(path: str) -> Path:
    root = Path(git(Path(path).resolve(), "rev-parse", "--show-toplevel")).resolve()
    if not root.is_dir():
        raise Error("Repository does not exist")
    return root

def route(task: str, risk: int | None = None):
    if risk is None:
        text = task.casefold()
        if any(w in text for w in ("auth", "permission", "paiement", "payment", "migration",
                                    "sécur", "secur", "delete", "supprim", "token", "revok", "révoqu")):
            risk = 3
        elif any(w in text for w in ("api", "database", "base de données", "architecture",
                                      "feature", "fonctionnalité", "plusieurs", "refactor", "system", "système")):
            risk = 2
        elif any(w in text for w in ("typo", "readme", "orthograph", "coquille", "couleur")):
            risk = 0
        else:
            risk = 1
    return {"risk": risk, "external_review": risk >= 2, "blind_review": risk >= 3,
            "note": "Keyword heuristic; coordinator must consider project context."}

def load_state(run: Path):
    state = read_json(run / "state.json")
    if state.get("version") != 1:
        raise Error("Unsupported state version; do not overwrite it")
    if repo_root(state["repo"]) != Path(state["repo"]):
        raise Error("Repository identity changed")
    return state

def save_state(run: Path, state, event: str, detail=None):
    state["updated_at"] = time.time()
    state["sequence"] = state.get("sequence", 0) + 1
    state["last_event"] = {"name": event, "detail": detail}
    atomic_json(run / "state.json", state)
    with (run / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"sequence": state["sequence"], "time": state["updated_at"],
                            "event": event, "detail": detail}, ensure_ascii=False) + "\n")
        f.flush()

def terminate(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait(timeout=10)

def execute(argv, cwd: Path, timeout=600, cancel: Path | None = None, env=None, input_text=None):
    """File-backed output and stdin avoid deadlocks; no shell or prompt in argv."""
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or "\0" in a for a in argv):
        raise Error("Command must be a nonempty array of strings")
    if Path(argv[0]).suffix.lower() in (".bat", ".cmd"):
        raise Error("Batch launcher unsupported; configure native executable or node + CLI entrypoint")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        if input_text is not None:
            inp.write(input_text.encode("utf-8"))
            inp.seek(0)
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=inp, stdout=out, stderr=err,
                                start_new_session=os.name != "nt")
        start = time.monotonic()
        try:
            while proc.poll() is None:
                if cancel is not None and cancel.exists():
                    raise Error("Run canceled")
                if time.monotonic() - start > timeout:
                    raise Error("Command timed out")
                time.sleep(0.1)
        except BaseException:
            terminate(proc)
            raise
        result = {"returncode": proc.returncode, "duration": round(time.monotonic() - start, 3)}
        for stream, key in ((out, "stdout"), (err, "stderr")):
            stream.seek(0)
            data = stream.read(2 * 1024 * 1024 + 1)
            result[key] = data[:2 * 1024 * 1024].decode("utf-8", "replace")
            result[key + "_truncated"] = len(data) > 2 * 1024 * 1024
        return result
