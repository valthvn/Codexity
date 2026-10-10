# Commands, installation and recovery

All examples use `python3 <skill>/scripts/runner.py`. On Windows use
`py -3 "<skill>\scripts\runner.py"` and quote absolute paths. Python 3.10+,
Git and authenticated agy are runtime prerequisites. No third-party Python
dependencies are needed.

## Install on another machine

Copy this complete skill folder, then use its installer with an explicit parent:

```powershell
py -3 .\codexity\scripts\install.py --skills-dir "$env:USERPROFILE\.codex\skills"
```

For a project-scoped installation, use the project's `.agents/skills` directory.
The installer refuses to overwrite an existing installation. Open a new Codex
conversation after installation and invoke `$codexity`. Model selection stays
with Codex. This skill is a host workflow, not a standalone autonomous builder.

## Mode and risk

Risk 0/1: Codex implementation and appropriate checks, external review optional.
Risk 2: plan review, host build/checks, fresh code review.
Risk 3: risk 2 plus an independent fresh blind pass on the final source snapshot.
Explicit loop always requires at least risk 2. Plan/review/investigate modes
always use the external provider. The route command is a keyword heuristic,
not an authority on risk; override using repository evidence.
Review mode defaults its committed baseline to HEAD; use --base to choose
another commit. Scope entries are individual relative file paths, not directories.

```text
route --task "Add access revocation"
doctor --repo <repo> [--config <provider.json>]
start --repo <repo> --task "..." --mode loop --risk 3 [--tdd]
start --repo <repo> --task "Review feature" --mode review --base HEAD --scope src/feature.py
set-plan --run <run> --file <plan.md>
review --run <run> --kind plan
build --run <run>
test --run <run> --commands-json '[["python3","-m","unittest","discover"]]'
review --run <run> --kind code
review --run <run> --kind blind
finding --run <run> --id C-... --status ACCEPTED --evidence "source and caller evidence"
review --run <run> --kind rebuttal --evidence-file <counter-evidence.md>
begin-fix --run <run>
finding --run <run> --id C-... --status FIXED --evidence "changed behavior and regression check"
test --run <run> --commands-json '[["python3","-m","unittest","discover"]]'
review --run <run> --kind final
review --run <run> --kind blind
finish --run <run>
```

Shell quoting for JSON differs on Windows. Prefer invoking Python with an argv
array through the host's process tool, or pass correctly quoted single-line JSON.
The checks execute arrays directly, without a shell. Choose commands from the
actual repository; never copy the example command into an unrelated project.
`--jobs` defaults to 1; 2/3 enable bounded parallel checks. Each check defaults
to 600 seconds, adjustable with `--timeout 1..1800`. Files changed by checks
invalidate the check record; rerun on a stable snapshot.

For TDD, start with `--tdd`, begin build, write the behavioral test, then use
`record-red --commands-json '[...]' --reason "expected assertion fails because ..."`.
Require a real positive exit failure on a stable snapshot. A missing executable,
timeout or cancellation does not count as the red phase. Implement and run green
checks afterward. The runner records ordering; the host verifies test meaning.

For documentation/cosmetic work at risk 0/1 only, `skip-tests --reason "..."`
records a reason instead of inventing a test. Risk 2/3 requires real passing checks.

## Reports and state

Default state root: `~/.codex/codexity-runs/<repository-hash>/<run-id>`.
Use `--state-root` only to select another external parent directory. Keep its
returned absolute run path for all subsequent commands. State is atomic and
versioned; events.jsonl is diagnostic. No rollback command exists: cancel never
undoes edits, and baseline files are evidence rather than an automatic restore.

Each report contains strict verdicts APPROVED/REVISE/BLOCKED, evidence tiers
FULL/DEGRADED/UNVERIFIED, hash bindings, findings, coverage and limitations.
IDs are generated from relative path and normalized title. They are exact
fingerprints, not semantic deduplication; the coordinator must reconcile differently
worded duplicates. Store dispositions and reasoning through the finding command.

`status --run ...` reads the phase and evaluates current gates.
`resume --run ...` performs the same integrity/staleness checks and reports the
next host action; it does not resume a Codex model conversation itself.
`cancel --run ...` creates a cancellation request checked by running subprocesses.
If a command currently owns the lock, cancellation remains pending until observed.
After a crash, a later command observes the request and releases the active run.
OS advisory locks release automatically when their owning process exits. Their
diagnostic PID metadata is never used to kill a process or steal a live lock.

Budgets: 3 plan attempts, 3 code attempts, 3 blind attempts, 2 final attempts,
2 rebuttals, 2 investigations, at most 12 external calls total and 2 fix rounds.
Errors after a provider call starts consume an attempt. Missing configuration
does not consume one. Repeated identical material findings across broad code/final
passes trigger a plateau stop. Nothing silently increases these limits.

finish returns PASS, PASS_WITH_ADVISORIES, FAIL or INCOMPLETE. Failed/incomplete
finish exits 2 and leaves the run recoverable; successful finish releases its active
slot. An investigation PASS means evidence was supplied, not code approval.
Keep normal Codex work available on provider failure, while marking this run's
independent validation incomplete.

## Development verification

Run `python3 -m unittest discover -s <skill>/tests -v` for offline protocol/state
tests using the fake CLI. Run doctor and a real review separately on the target
machine. Fake-provider tests do not prove real account, quota, model or Windows
behavior. The fake CLI must never be configured for real project approval.
