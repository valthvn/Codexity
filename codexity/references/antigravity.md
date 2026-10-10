# Antigravity adapter

Use an installed, authenticated Antigravity CLI on the SAME machine as Codex's
terminal execution. A CLI on a Windows host is not accessible from a remote Codex
container automatically. The current environment may lack agy even though the
skill is installed; run doctor locally before the first real review.

Run `agy` interactively to authenticate with the user's Google account, then
`agy models` to verify the desired slug. Default to `gemini-3.8-flash-high` with
effort `high`; keep Codex's current model unchanged. Do not substitute another
model silently. Cached login is used; no API keys are required by this adapter.

The runner sends one stdin user event with `--input-format stream-json`, reads
`--output-format stream-json`, and requires exactly one SUCCESS result, a valid
conversation ID, and schema-valid structured_output (or strictly parsed JSON
response). It uses `--json-schema`, `--model`, `--effort` and `--sandbox`. Plan
rounds may resume their exact recorded ID; code, blind and final reviews always
start fresh. Never use `--continue` or a most-recent-session alias.

Optionally create a local JSON provider configuration outside the repository:

```json
{
  "command": ["agy"],
  "model": "gemini-3.8-flash-high",
  "effort": "high",
  "timeout": 600
}
```

Pass `--config "absolute/config.json"` to doctor and start. Commands must be a
native executable or an interpreter plus one existing absolute entrypoint. For
Windows .cmd/.bat wrappers, use the actual installed Node CLI entrypoint with
`["C:/.../node.exe", "C:/.../verified-cli-entrypoint.js"]`. Discover that path
from the installed package; never invent it. The adapter refuses batch wrappers
to avoid Windows shell interpolation. Python, Git and a native launcher are
required. Native Windows execution must be verified on the user's machine.

Doctor checks help capabilities and model availability; it does not prove login,
credit availability or a functioning OS sandbox. A real review is needed for that.
Headless tools can be denied while the CLI still exits successfully. Such notices,
omitted changed files, unsupported entries or source drift degrade the report and
cannot satisfy a gate. Permission restrictions may require source-only review;
do not use a permission-bypass flag to obtain a passing report.

Official protocol reference, checked 2026-10-10:
https://www.antigravity.google/docs/cli/headless/
Model reference: https://www.antigravity.google/docs/models/
