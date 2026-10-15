"""
Usage: .venv/bin/python ./scripts/extract_cset_candidates.py [--cset-path PATH] [--output-dir DIR] [--force] [--no-pull]

  --output-dir  default: data/csf/bank_build

Deterministic extraction of CSF 2.0 question candidates from the CSET SQL migration files
(CSETWebApi/.../VersionUpgrader/SQL). Domain-independent: writes data/csf/bank_build/cset_candidates.json,
which build_question_bank.py later routes per domain. No judgement happens here.

What it reads (migration files processed in filename order):
  MATURITY_REFERENCES  INSERT  (Gen_File_Id 692 = CSF 2.0)  question -> subcategory mappings
  MATURITY_REFERENCES  DELETE                               mappings removed later (subtracted)
  MATURITY_QUESTIONS   INSERT                               question text, category, source model
  MATURITY_QUESTIONS   UPDATE                               later changes to Question_Text / Is_Answerable
  MATURITY_QUESTIONS   DELETE                               questions removed entirely (dropped)
  MATURITY_MODELS      INSERT                               model id -> name (e.g. 1 = ACET)

Freshness: compares the CSET HEAD with the commit stored in the candidates file. Same -> exit.
Different but no migration .sql file under SQL_SUBPATH changed -> patch the stored commit only. Otherwise re-extract.

Each question carries deterministic `flags`: empty_text, truncated, not_answerable, statement_only.
`statement_only` = no Question_Text but practice fields (SSG IT / CPG2 models); the content is kept
under `practice` and an agent step later rewrites it as a question.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import BANK_BUILD  # noqa: E402
import audit  # noqa: E402

DEFAULT_CSET_PATH = "~/workstuff/cset"
SQL_SUBPATH = "CSETWebApi/CSETWeb_Api/CSETWebCore.UpgradeLibrary/VersionUpgrader/SQL"
CSF_GEN_FILE_ID = 692

# Column order of MATURITY_QUESTIONS inserts that carry no column list (old migrations).
DEFAULT_QUESTION_COLUMNS = ["Mat_Question_Id", "Question_Title", "Question_Text", "Supplemental_Info",
                            "Category", "Sub_Category", "Maturity_Level_Id", "Sequence", "Maturity_Model_Id"]

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def git(cset_path: Path, *args) -> str:
    result = subprocess.run(["git", "-C", str(cset_path), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def sql_changed(cset_path: Path, old: str, new: str) -> bool:
    """True if a migration .sql file this script reads (under SQL_SUBPATH) differs between two CSET commits.
    Raises RuntimeError if git cannot compare them (for example an unknown commit)."""
    return bool(git(cset_path, "diff", "--name-only", old, new, "--", f"{SQL_SUBPATH}/*.sql"))


def read_sql_file(f: Path) -> str:
    raw = f.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be")
    return raw.decode("utf-8", errors="replace")


# ── SQL value tokeniser ───────────────────────────────────────────────────────

def parse_value(s: str, i: int):
    """Parse one SQL literal at s[i]. Returns (python_value, next_index)."""
    while i < len(s) and s[i] in " \t":
        i += 1
    if s.startswith("N'", i) or s.startswith("'", i):
        i += 2 if s[i] == "N" else 1
        buf = []
        while i < len(s):
            if s[i] == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                return "".join(buf), i + 1
            buf.append(s[i])
            i += 1
        return "".join(buf), i
    if s.startswith("NULL", i):
        return None, i + 4
    m = NUMBER.match(s, i)
    if m:
        txt = m.group()
        return (float(txt) if "." in txt else int(txt)), m.end()
    # anything else (function call, hex, ...): read to the next top-level comma/paren
    depth, j = 0, i
    while j < len(s):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            if depth == 0:
                break
            depth -= 1
        elif s[j] == "," and depth == 0:
            break
        j += 1
    return s[i:j].strip(), j


def parse_values(s: str, i: int) -> list:
    """Parse a comma-separated literal list starting at s[i] up to the closing ')'."""
    vals = []
    while i < len(s):
        v, i = parse_value(s, i)
        vals.append(v)
        while i < len(s) and s[i] in " \t":
            i += 1
        if i < len(s) and s[i] == ",":
            i += 1
            continue
        break
    return vals


def parse_insert(line: str, default_cols: list[str] | None = None) -> dict | None:
    m = re.search(r"INSERT INTO \[dbo\]\.\[\w+\]\s*(?:\((.*?)\))?\s*VALUES\s*\(", line)
    if not m:
        return None
    cols = re.findall(r"\[(\w+)\]", m.group(1)) if m.group(1) else (default_cols or [])
    vals = parse_values(line, m.end())
    return dict(zip(cols, vals))


def parse_update_set(line: str) -> tuple[dict, str]:
    """Parse 'UPDATE ... SET [A]=v, [B]=v WHERE ...' -> ({A: v, B: v}, where_clause)."""
    m = re.search(r"\bSET\s+", line)
    if not m:
        return {}, ""
    i, out = m.end(), {}
    while True:
        cm = re.compile(r"\s*\[(\w+)\]\s*=\s*").match(line, i)
        if not cm:
            break
        v, i = parse_value(line, cm.end())
        out[cm.group(1)] = v
        while i < len(line) and line[i] in " \t":
            i += 1
        if i < len(line) and line[i] == ",":
            i += 1
        else:
            break
    return out, line[i:]


# ── extraction ────────────────────────────────────────────────────────────────

STATEMENT_START = ("INSERT INTO", "UPDATE ", "DELETE FROM")


def join_multiline_statements(lines: list[str]) -> list[str]:
    """
    Question text often contains line breaks, so one INSERT/UPDATE spans several lines. A statement
    is complete once its quotes balance ('' escapes keep the parity), so keep appending lines until
    they do. Without this, text is cut at the first line break.
    """
    out: list[str] = []
    buf: str | None = None
    for line in lines:
        if buf is None:
            if line.lstrip().startswith(STATEMENT_START) and line.count("'") % 2 == 1:
                buf = line
            else:
                out.append(line)
        else:
            buf += "\n" + line
            if buf.count("'") % 2 == 0:
                out.append(buf)
                buf = None
    if buf is not None:
        out.append(buf)
    return out


def read_sql_lines(cset_sql: Path) -> list[str]:
    """One entry per SQL statement (multi-line statements joined), files in name order."""
    lines: list[str] = []
    for sql_file in sorted(cset_sql.glob("*.sql")):
        lines.extend(join_multiline_statements(read_sql_file(sql_file).splitlines()))
    return lines


def net_active_pairs(lines: list[str]) -> set[tuple[int, str]]:
    ins_pat = re.compile(r"VALUES \((\d+), %d, N?'([A-Z]{2}\.[A-Z]{2}-\d{2})'" % CSF_GEN_FILE_ID)
    del_pat = re.compile(r"\[Mat_Question_Id\] = (\d+).*?\[Section_Ref\] = N?'([A-Z]{2}\.[A-Z]{2}-\d{2})'")
    inserts, deletes = set(), set()
    for line in lines:
        if "[MATURITY_REFERENCES]" not in line:
            continue
        if "INSERT INTO" in line and f", {CSF_GEN_FILE_ID}, " in line:
            m = ins_pat.search(line)
            if m:
                inserts.add((int(m.group(1)), m.group(2)))
        elif "DELETE FROM" in line and f"Gen_File_Id] = {CSF_GEN_FILE_ID}" in line:
            m = del_pat.search(line)
            if m:
                deletes.add((int(m.group(1)), m.group(2)))
    return inserts - deletes


def extract_models(lines: list[str]) -> dict[int, str]:
    models = {}
    for line in lines:
        if "INSERT INTO [dbo].[MATURITY_MODELS]" in line:
            row = parse_insert(line)
            if row and row.get("Maturity_Model_Id") is not None:
                models[int(row["Maturity_Model_Id"])] = row.get("Model_Name")
    return models


def extract_questions(lines: list[str], qids: set[int]) -> tuple[dict[int, dict], dict]:
    """Replay MATURITY_QUESTIONS INSERT / UPDATE / DELETE for qids, in migration order."""
    state: dict[int, dict] = {}
    stats = {"inserted": 0, "text_updates": 0, "answerable_updates": 0, "deleted": 0}
    id_in_where = re.compile(r"\[Mat_Question_Id\]\s*=\s*(\d+)")

    for line in lines:
        if "[MATURITY_QUESTIONS]" not in line:
            continue
        if "INSERT INTO" in line:
            m = re.search(r"VALUES\s*\((\d+)", line)
            if not m or int(m.group(1)) not in qids:
                continue
            row = parse_insert(line, DEFAULT_QUESTION_COLUMNS)
            if row:
                state.setdefault(int(m.group(1)), row)
                stats["inserted"] += 1
        elif "UPDATE" in line:
            m = id_in_where.search(line)
            if not m or int(m.group(1)) not in qids or int(m.group(1)) not in state:
                continue
            sets, _ = parse_update_set(line)
            row = state[int(m.group(1))]
            if "Question_Text" in sets and sets["Question_Text"]:
                row["Question_Text"] = sets["Question_Text"]
                stats["text_updates"] += 1
            if "Is_Answerable" in sets:
                row["Is_Answerable"] = sets["Is_Answerable"]
                stats["answerable_updates"] += 1
        elif "DELETE FROM" in line:
            m = id_in_where.search(line)
            if m and int(m.group(1)) in state:
                del state[int(m.group(1))]
                stats["deleted"] += 1
    return state, stats


def clean_text(raw: str | None) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()


PRACTICE_FIELDS = {"Security_Practice": "security_practice", "Outcome": "outcome", "Scope": "scope",
                   "Risk_Addressed": "risk_addressed", "Recommend_Action": "recommend_action"}


def practice_fields(row: dict) -> dict:
    out = {name: clean_text(row.get(col)) for col, name in PRACTICE_FIELDS.items()}
    return {k: v for k, v in out.items() if v}


def question_flags(raw_text: str | None, is_answerable, practice: dict) -> list[str]:
    text = clean_text(raw_text)
    flags = []
    if not text:
        flags.append("statement_only" if practice else "empty_text")
    elif text.endswith((":", ",")) or len(text) < 25:
        flags.append("truncated")
    if is_answerable in (0, False, "0"):
        flags.append("not_answerable")
    return flags


def build_candidates(lines: list[str], cset_commit: str) -> dict:
    pairs = net_active_pairs(lines)
    qids = {q for q, _ in pairs}
    models = extract_models(lines)
    rows, stats = extract_questions(lines, qids)

    questions = {}
    for qid in sorted(rows):
        r = rows[qid]
        model_id = r.get("Maturity_Model_Id")
        practice = practice_fields(r)
        questions[str(qid)] = {
            "question_text": clean_text(r.get("Question_Text")),
            "title": r.get("Question_Title"),
            "category": r.get("Category"),
            "sub_category": r.get("Sub_Category"),
            "model_id": model_id,
            "model_name": models.get(model_id),
            "is_answerable": r.get("Is_Answerable"),
            "practice": practice,
            "flags": question_flags(r.get("Question_Text"), r.get("Is_Answerable"), practice),
        }
    mappings = [{"qid": q, "subcategory_id": s} for q, s in sorted(pairs) if str(q) in questions]
    return {
        "cset_commit": cset_commit,
        "extracted_on": date.today().isoformat(),
        "stats": {**stats, "net_active_pairs": len(pairs), "questions": len(questions),
                  "dropped_deleted_questions": len(qids) - len(questions)},
        "models": {str(k): v for k, v in sorted(models.items())},
        "questions": questions,
        "mappings": mappings,
    }


def freshness(out_path: Path, cset_path: Path, cset_commit: str) -> str:
    """'extract' | 'current' | 'patched'."""
    if not out_path.exists():
        return "extract"
    data = json.loads(out_path.read_text())
    stored = data.get("cset_commit")
    if stored == cset_commit:
        return "current"
    if not stored or sql_changed(cset_path, stored, cset_commit):
        return "extract"
    data["cset_commit"] = cset_commit
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return "patched"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cset-path", default=DEFAULT_CSET_PATH)
    parser.add_argument("--output-dir", default=str(BANK_BUILD))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-pull", action="store_true")
    args = parser.parse_args()

    cset_path = Path(args.cset_path).expanduser()
    cset_sql = cset_path / SQL_SUBPATH
    out_path = Path(args.output_dir) / "cset_candidates.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ev = audit.begin(out_path.parent / "audit.jsonl", "extract_cset_candidates",
                     {"cset_path": str(cset_path), "force": args.force, "no_pull": args.no_pull})
    if not cset_sql.is_dir():
        ev.fail(f"[extract_cset_candidates] ERROR: CSET SQL folder not found: {cset_sql}")

    try:
        if not args.no_pull:
            git(cset_path, "pull", "--ff-only")
        cset_commit = git(cset_path, "rev-parse", "HEAD")
    except RuntimeError as e:
        ev.fail(f"[extract_cset_candidates] ERROR: could not update CSET repo at {cset_path}: {e}. "
                "Resolve manually before rebuilding.")

    status = "extract" if args.force else freshness(out_path, cset_path, cset_commit)
    if status == "current":
        print(f"Candidates up to date (commit {cset_commit[:8]}). Nothing to extract.")
        ev.finish(outputs=[out_path], detail="up to date, nothing extracted", cset_commit=cset_commit)
        return
    if status == "patched":
        print(f"SHA advanced but no SQL changed. Stored commit updated to {cset_commit[:8]}.")
        ev.finish(outputs=[out_path], detail="commit advanced, no SQL changed; stored commit updated", cset_commit=cset_commit)
        return

    data = build_candidates(read_sql_lines(cset_sql), cset_commit)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    s = data["stats"]
    flag_counts: dict[str, int] = {}
    for q in data["questions"].values():
        for f in q["flags"]:
            flag_counts[f] = flag_counts.get(f, 0) + 1
    no_model = sum(1 for q in data["questions"].values() if q["model_id"] is None)
    print(f"Extracted: {out_path}\nCSET commit: {cset_commit}\n"
          f"Questions: {s['questions']} | mappings: {s['net_active_pairs']} | text updates: {s['text_updates']} "
          f"| dropped (deleted in CSET): {s['dropped_deleted_questions']}\n"
          f"Flags: {flag_counts} | missing model id: {no_model}")
    ev.finish(outputs=[out_path], detail=f"extracted {s['questions']} questions, {s['net_active_pairs']} mappings; flags {flag_counts}",
              cset_commit=cset_commit)


if __name__ == "__main__":
    main()
