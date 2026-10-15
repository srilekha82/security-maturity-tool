"""
Shared audit trail. Import this from any script; there is nothing to run.

Every script run and every agent step appends ONE line to an audit.jsonl, so a run can be read back
as a timeline of what happened, who did it (script / agent / human), with what, and how it ended.
Where the file lives:
  runs/<Org>_<date>/audit.jsonl     an engagement run
  data/csf/bank_build/audit.jsonl   question bank build (extract, build, judging)
  data/audit.jsonl                  reference data refresh and freshness checks

Usage in a script (log_path is one of the files above):

    ev = audit.begin(log_path, "my_script", args={...})       # at the start, once the arguments are known
    ...
    ev.finish(inputs=[...], outputs=[...], detail="one line")  # on success
    ev.fail("message")                                          # error: logs, prints the message, exits 1
    ev.pending("what the agent must do", outputs=[...])         # needs an agent: logs, exits 2

If a script exits or crashes without calling finish, an "incomplete" line is still written (atexit), so
a failed or aborted step never goes missing. Each line records files as {path, sha}; paths are relative
to the log's folder, then to the repo root. Lines are only ever appended.

Any new script or agent step should call begin/finish. Agent steps use `record_judgements.py log`,
which does it for them (actor "agent").
"""

import atexit
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import REPO_ROOT  # noqa: E402


def sha(path) -> str | None:
    p = Path(path) if path else None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p and p.is_file() else None


def _ref(path, base: Path) -> dict:
    p = Path(path)
    for root in (base, REPO_ROOT):
        try:
            return {"path": str(p.resolve().relative_to(root.resolve())), "sha": sha(p)}
        except ValueError:
            continue
    return {"path": str(p), "sha": sha(p)}


class Event:
    def __init__(self, log_path, step: str, actor: str, args: dict | None):
        self.log_path, self.step, self.actor = Path(log_path), step, actor
        self.args = args or {}
        self.started = datetime.now(timezone.utc)
        self.done = False
        atexit.register(self._incomplete)

    def finish(self, status: str = "ok", inputs=(), outputs=(), detail: str = "", **extra) -> None:
        if self.done:
            return
        self.done = True
        base = self.log_path.parent
        record = {
            "started": self.started.isoformat(),
            "ended": datetime.now(timezone.utc).isoformat(),
            "actor": self.actor,
            "step": self.step,
            "args": self.args,
            "status": status,
            "detail": str(detail)[:500],
            "inputs": [_ref(p, base) for p in inputs],
            "outputs": [_ref(p, base) for p in outputs],
            **extra,
        }
        base.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def fail(self, message: str, inputs=(), outputs=()) -> None:
        self.finish("error", inputs, outputs, detail=message)
        sys.exit(message)

    def reject(self, problems: list, what: str, inputs=(), status: str = "error", verb: str = "written") -> None:
        """The file or input `what` has problems: report them, log the step with `status`, exit 1, nothing written."""
        report_problems(self.step, problems, what, verb)
        self.finish(status, inputs, detail=f"{len(problems)} problems in {what}: {problems[:3]}")
        sys.exit(1)

    def pending(self, detail: str, inputs=(), outputs=()) -> None:
        self.finish("pending", inputs, outputs, detail=detail)
        sys.exit(2)

    def _incomplete(self) -> None:
        if not self.done:
            self.finish("incomplete", detail="exited before finishing (error, or an unhandled exception)")


def report_problems(label: str, problems: list, what: str, verb: str = "written", limit: int = 40) -> None:
    """Print "[label] N problems in <what>, nothing <verb>:" and the problems (the first `limit`) to stderr."""
    print(f"[{label}] {len(problems)} problems in {what}, nothing {verb}:", file=sys.stderr)
    for p in problems[:limit]:
        print(f"  - {p}", file=sys.stderr)
    if len(problems) > limit:
        print(f"  … and {len(problems) - limit} more", file=sys.stderr)


def begin(log_path, step: str, args: dict | None = None, actor: str = "script") -> Event:
    return Event(log_path, step, actor, args)


def run_log(run_dir) -> Path:
    return Path(run_dir) / "audit.jsonl"


def write_once_record(log_dir, step: str, record: dict) -> Path:
    """Write `record` as <log_dir>/<UTC timestamp>_<step>.json and never overwrite an existing record.
    The generic half of the judgement log: callers build the record (model, prompt hash, output snapshot)."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{step}.json"  # microseconds: no clash within a second
    with open(path, "x") as f:  # "x": fails rather than overwrite
        json.dump(record, f, indent=2, ensure_ascii=False)
    return path


def record_agent_output(*, log_path, log_dir, step: str, args: dict, file, validate, store, model: str,
                        session: str | None = None, prompts=(), log_name=None, extra_inputs=(), extra_record=None,
                        snapshot_key: str = "output_snapshot") -> tuple[Path, str]:
    """The one recording contract for agent output (used by record_judgements.py bank mode and record_ai_bank.py).

    Reads the agent's JSON `file`, calls validate(data) -> list of problems, and if there are any rejects the WHOLE
    file: audit line "rejected", nothing stored, exit 1. Otherwise calls store(data) -> (store path, one-line summary),
    writes a write-once record (model, session, prompt hashes, input and store hashes, the output exactly as submitted
    under `snapshot_key`, plus `extra_record`) to `log_dir` as <timestamp>_<log_name>.json, and appends an audit line
    (actor "agent"). `prompts` are repo-relative paths; `log_name` is a string or a function of the data (default: step).
    """
    ev = begin(log_path, step, {**args, "model": model, "session": session}, actor="agent")
    file = Path(file)
    try:
        data = json.loads(file.read_text())
    except (OSError, ValueError) as e:
        ev.fail(f"[{step}] ERROR: cannot read {file} as JSON: {e}")

    errors = validate(data)
    if errors:
        ev.reject(errors, file.name, [file], status="rejected", verb="stored")

    store_path, summary = store(data)
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "step": step, "decided_by": "agent",
        "model": model, "session": session,
        "prompts": [{"path": p, "sha": sha(REPO_ROOT / p)} for p in prompts],
        "input_file": {"path": str(file), "sha": sha(file)},
        "store": _ref(store_path, REPO_ROOT),
        snapshot_key: data,  # the file can be replaced later; this copy cannot
        **(extra_record or {}),
    }
    name = log_name(data) if callable(log_name) else (log_name or step)
    log_file = write_once_record(log_dir, name, record)
    print(f"[{step}] {summary} → {_ref(store_path, REPO_ROOT)['path']}; audit record → {log_file.name}")
    ev.finish(inputs=[file, *[REPO_ROOT / p for p in prompts], *extra_inputs], outputs=[store_path, log_file], detail=summary)
    return store_path, summary
