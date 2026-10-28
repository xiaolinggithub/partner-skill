#!/usr/bin/env python3
"""Fixed dispatch and evidence-based acceptance for Partner identity tryouts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("tryout_config", SCRIPT_DIR / "partner-config.py")
config = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = config
SPEC.loader.exec_module(config)
ROLES = ("fast_worker", "deep_reasoner", "arbiter")
FAST_TASK = ('Sort the keys of this JSON object alphabetically at every nesting level '
             'and return only the formatted result:\n'
             '{"b":{"z":1,"a":{"c":3}},"a":[2,1],"c":"x"}')
REASON_TASK = ("A CLI tool stores per-project config. A is one dotfile per project in the repo "
              "(committed); B is one central file in the user's home keyed by project path. "
              "Name the decisive tradeoff and pick one for a tool whose users frequently "
              "rename and move project directories. Conclusion first, then at most three "
              "sentences of reasoning.")


EXPECTED_FAST = {"a": [2, 1], "b": {"a": {"c": 3}, "z": 1}, "c": "x"}


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save(path, run):
    config.atomic_write(path, json.dumps(run, ensure_ascii=False, indent=2) + "\n")


def task_prompt(role):
    return (FAST_TASK if role == "fast_worker" else REASON_TASK) + "\n\nDo not edit files or run commands. Answer only."


def resolve_roles(repo, host, selected):
    resolved = config.resolve_config(repo, host)
    identities = resolved["hosts"][host]["identities"]
    roles = {}
    for role in ([selected] if selected else ROLES):
        if role not in identities:
            raise ValueError(f"{role} is not configured; run 搭子，配置 first")
        roles[role] = dict(identities[role], scope=None)
    for scope, path in (("global", config.global_config_path()), ("project", config.project_config_path(repo))):
        if path.is_file():
            parsed = config.validate_config(path.read_text(), host, path=path)
            for role in parsed["hosts"][host]["identities"]:
                if role in roles:
                    roles[role]["scope"] = scope
    return resolved["source"], roles


def delegate(args, output=None):
    command = ["bash", str(SCRIPT_DIR / "delegate-codex.sh"), *map(str, args)]
    if output is None:
        result = subprocess.run(command, capture_output=True, text=True)
        stdout = result.stdout
    else:
        with output.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, text=True)
        stdout = output.read_text()
    # status returns nonzero for terminal failures; its state is still evidence.
    if result.returncode and args[0] != "status":
        raise RuntimeError(result.stderr.strip() or f"delegate {args[0]} exited {result.returncode}")
    return stdout


def start(repo, host, selected):
    repo = repo.resolve()
    source, roles = resolve_roles(repo, host, selected)
    root = repo / ".partner" / "receipts"
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="tryout-", dir=root))
    path = folder / "run.json"
    run = {"host": host, "repo": str(repo), "config_source": source,
           "started_at": utc_now(), "roles": roles}
    for row in roles.values():
        row["state"] = "pending"
    save(path, run)
    for role, row in roles.items():
        prompt = task_prompt(role)
        if row["backend"] == "claude":
            row.update(state="awaiting_native_agent", native_agent={
                "model": row["model"], "effort": row["effort"], "prompt": prompt})
        else:
            prompt_path = folder / (role + ".md")
            prompt_path.write_text(prompt)
            row["state"] = "submitting"
            save(path, run)
            try:
                # submit starts background jobs; never wait before dispatching the next role.
                job = delegate(["submit", "--repo", repo, "--host", host, "--role", role,
                    "--model", row["model"], "--effort", row["effort"], "--read-only",
                    "--label", "tryout-" + role, "--prompt-file", prompt_path],
                    output=folder / (role + ".submission")).strip()
                if not re.fullmatch(r"job-[A-Za-z0-9._-]+", job):
                    raise ValueError("missing job ID; inspect submission evidence before any rerun")
                row.update(job_id=job, state="RUNNING")
            except (OSError, ValueError, RuntimeError) as error:
                row.update(state="submission_failed", error=str(error))
        save(path, run)
    run["dispatched_at"] = utc_now()
    save(path, run)
    return path, run


def native_transcript(path, role):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    first = next((row for row in rows if row.get('type') == 'user'), {})
    if first.get('message', {}).get('content') != task_prompt(role):
        raise ValueError('native transcript does not contain this role\'s exact task')
    evidence = {'source': str(path), 'completed': False, 'observed_models': [],
                'execution': {'returncode': None, 'elapsed_seconds': None}}
    handback = None
    for row in rows:
        message = row.get('message', {})
        if row.get('type') == 'assistant' and message.get('model'):
            model = message['model']
            if model not in evidence['observed_models']:
                evidence['observed_models'].append(model)
        content = message.get('content', [])
        for block in content if isinstance(content, list) else []:
            if row.get('type') == 'assistant' and block.get('type') == 'tool_use' and block.get('name') == 'SubagentHandback':
                handback = block['id']
                evidence['agent_message'] = block['input']['message']
                evidence.update(completed=False, execution={'returncode': None, 'elapsed_seconds': None})
            if (row.get('type') == 'user' and block.get('type') == 'tool_result'
                    and handback and block.get('tool_use_id') == handback):
                # shortcut: only a confirmed handback proves completion; other hosts use explicit Agent evidence.
                result = block.get('content', [])
                raw = result if isinstance(result, str) else ''.join(
                    part.get('text', '') for part in result if part.get('type') == 'text')
                try:
                    success = json.loads(raw).get('success') is True and not block.get('is_error')
                except (ValueError, AttributeError):
                    success = False
                evidence['completed'] = bool(success)
                evidence['execution']['returncode'] = 0 if success else None
                if success:
                    try:
                        start = datetime.fromisoformat(first['timestamp'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                        if end >= start:
                            evidence['execution'].update(started_at=first['timestamp'],
                                finished_at=row['timestamp'], elapsed_seconds=(end - start).total_seconds())
                    except (KeyError, ValueError, TypeError):
                        pass
    return evidence


def collect(path, wait_seconds, agent_results, agent_transcripts=None):
    if not 0 <= wait_seconds <= 60:
        raise ValueError("wait-seconds must be between 0 and 60; collect again to keep waiting")
    run = json.loads(path.read_text())
    agent_transcripts = agent_transcripts or {}
    if set(agent_results) & set(agent_transcripts):
        raise ValueError("use one native evidence source per role")
    if (set(agent_results) | set(agent_transcripts)) - set(run["roles"]):
        raise ValueError("agent-result names a role outside this run")
    deadline = time.monotonic() + wait_seconds
    while True:
        running = False
        for role, row in run["roles"].items():
            if role in agent_results or role in agent_transcripts:
                if row["backend"] != "claude":
                    raise ValueError("agent-result cannot replace a Codex job")
                evidence = (native_transcript(Path(agent_transcripts[role]), role)
                            if role in agent_transcripts else json.loads(Path(agent_results[role]).read_text()))
                if not isinstance(evidence.get("completed"), bool) or not evidence.get("source"):
                    raise ValueError("native evidence requires completed boolean and source")
                evidence.setdefault("execution", {}).setdefault("elapsed_seconds", None)
                evidence.setdefault("observed_models", [])
                row.update(evidence=evidence, state="DONE" if evidence["completed"] else "RUNNING")
            elif row["backend"] == "codex":
                if not row.get("job_id"):
                    submission = path.parent / (role + ".submission")
                    job = submission.read_text().strip() if submission.exists() else ""
                    if re.fullmatch(r"job-[A-Za-z0-9._-]+", job):
                        row["job_id"] = job
                if row.get("job_id"):
                    args = [row["job_id"], "--repo", run["repo"]]
                    try:
                        status = delegate(["status", *args])
                        states = re.findall(r"(?m)^state: (RUNNING|DONE|FAILED|CANCELLED)$", status)
                        if len(states) != 1:
                            raise ValueError("missing terminal/running state")
                        row["state"] = states[0]
                        if row["state"] != "RUNNING":
                            row["evidence"] = json.loads(delegate(["result", *args, "--json"]))
                        row.pop("collection_error", None)
                    except (OSError, ValueError, RuntimeError) as error:
                        row.update(state="collection_failed", collection_error=str(error))
            evidence = row.get("evidence", {})
            returncode = evidence.get("execution", {}).get("returncode")
            succeeded = (row["state"] == "DONE" and type(returncode) is int and returncode == 0
                         and (row["backend"] != "claude" or evidence.get("completed") is True))
            row["process_succeeded"] = bool(succeeded)
            row["passed"] = False
            if role == "fast_worker" and "agent_message" in evidence:
                row["validation"] = validate_fast_worker(evidence["agent_message"])
                row["passed"] = succeeded and row["validation"]["passed"]
            running |= row["state"] == "RUNNING" and row["backend"] == "codex"
        run["collected_at"] = utc_now()
        save(path, run)
        if not running or time.monotonic() >= deadline:
            return run
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def reject_constant(value: str):
    raise ValueError("non-finite JSON number")


def keys_are_sorted(value) -> bool:
    if isinstance(value, dict):
        return list(value) == sorted(value) and all(keys_are_sorted(v) for v in value.values())
    if isinstance(value, list):
        return all(keys_are_sorted(v) for v in value)
    return True


def validate_fast_worker(text: str) -> dict:
    result = {"passed": False, "format_valid": False, "content_valid": False,
              "keys_sorted": False, "errors": []}
    lines = text.strip().splitlines()
    fenced = len(lines) >= 3 and lines[0] in ("```", "```json") and lines[-1] == "```"
    if fenced:
        result["errors"].append("markdown_fence")
        text = "\n".join(lines[1:-1])
    try:
        value = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, RecursionError) as error:
        result["errors"].append("invalid_json: " + str(error))
        return result
    result["format_valid"] = not fenced
    # Dict equality alone treats true as 1; preserve JSON value types as well.
    result["content_valid"] = json.dumps(value, sort_keys=True) == json.dumps(EXPECTED_FAST, sort_keys=True)
    result["keys_sorted"] = keys_are_sorted(value)
    if not result["content_valid"]:
        result["errors"].append("content_mismatch")
    if not result["keys_sorted"]:
        result["errors"].append("keys_not_sorted")
    result["passed"] = all(result[key] for key in ("format_valid", "content_valid", "keys_sorted"))
    return result


def finalize(path, decisions):
    run = json.loads(path.read_text())
    if not isinstance(decisions, dict) or set(decisions) - set(run['roles']):
        raise ValueError('judgments must be an object naming only roles in this run')
    current = {}
    try:
        # One-role runs must not require the two unused identities.
        for role in run['roles']:
            _, resolved = resolve_roles(Path(run['repo']), run['host'], role)
            current.update(resolved)
    except (OSError, config.ConfigError, ValueError) as error:
        run['config_error'] = str(error)
    for role, row in run['roles'].items():
        decision = decisions.get(role, {})
        if not isinstance(decision, dict):
            raise ValueError('each role judgment must be an object')
        for field in ('accepted', 'routing_established'):
            if field in decision and not isinstance(decision[field], bool):
                raise ValueError(f'{role}.{field} must be boolean')
        if decision.get('verification_write', 'pending') not in ('pending', 'denied'):
            raise ValueError('verification_write may be pending or denied; successful writes are read back')
        accepted = (row.get('validation', {}).get('passed', False) if role == 'fast_worker'
                    else decision.get('accepted') is True and bool(decision.get('reason', '').strip()))
        row['passed'] = bool(row.get('process_succeeded') and accepted)
        row['judgment'] = decision
        row['verified_this_run'] = False
        row['verification_write'] = decision.get('verification_write', 'pending')
        row.pop('verification_command', None)
        live = current.get(role, {})
        unchanged = all(live.get(key) == row.get(key) for key in ('backend', 'model', 'effort', 'scope'))
        row['routing_unchanged'] = unchanged
        eligible = row['passed'] and decision.get('routing_established') is True and unchanged
        if eligible:
            try:
                stamp = datetime.fromisoformat(live.get('verified_at', '').replace('Z', '+00:00'))
                row['verified_this_run'] = (live.get('verified') is True and
                    datetime.fromisoformat(run['started_at']) <= stamp <= datetime.now(timezone.utc))
            except (ValueError, TypeError):
                pass
            if row['verified_this_run']:
                row['verification_write'] = 'confirmed'
            elif row.get('scope') in ('project', 'global'):
                row['verification_command'] = shlex.join([
                    sys.executable, str(SCRIPT_DIR / 'partner-config.py'), '--host', run['host'],
                    '--repo', run['repo'], '--scope', row['scope'], 'set', '--role', role,
                    '--verified', '--verified-at', utc_now()])
        if not row['passed']:
            row['verification_write'] = 'not_eligible'
    run['finalized_at'] = utc_now()
    run['elapsed_seconds'] = (datetime.fromisoformat(run['finalized_at']) -
                              datetime.fromisoformat(run['started_at'])).total_seconds()
    save(path, run)
    return run


def make_receipt(path, run, args):
    used = [{'role': role, 'host': run['host'], 'model': row['model'],
             'effort': row['effort'], 'verified': row['verified_this_run']}
            for role, row in run['roles'].items() if row.get('job_id') or row.get('evidence')]
    checks = '; '.join(f"{role}={'PASS' if row['passed'] else 'FAIL/PENDING'}"
                       for role, row in run['roles'].items())
    anomalies = '; '.join(f"{role}: verification_write={row['verification_write']}"
                          for role, row in run['roles'].items()
                          if row['verification_write'] != 'confirmed') or 'none'
    command = [sys.executable, str(SCRIPT_DIR / 'make-receipt.py'), '--phase', 'review',
        '--claude-session', args.claude_session, '--reused', 'n/a',
        '--new-claude-p', args.new_claude_p, '--codex-passes', '0', '--checks', checks,
        '--anomalies', anomalies, '--host', run['host'], '--config-source', run['config_source'],
        '--direction', 'claude-driven' if run['host'] == 'claude_code' else 'codex-driven',
        '--codex-jobs', str(sum(bool(row.get('job_id')) for row in run['roles'].values())),
        '--roles-used', json.dumps(used), '--repo', run['repo'], '--save']
    if args.monitoring_level:
        command += ['--monitoring-level', args.monitoring_level]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    receipt = path.parent / 'receipt.md'
    receipt.write_text(result.stdout)
    return str(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    begin = sub.add_parser('start', help='Start fixed tasks once; persist IDs and return native-agent packets.')
    begin.add_argument('--host', choices=config.HOSTS, required=True)
    begin.add_argument('--repo', type=Path, required=True)
    begin.add_argument('--role', choices=ROLES)
    gather = sub.add_parser('collect', help='Observe an existing run; never retry or resubmit.')
    gather.add_argument('run', type=Path)
    gather.add_argument('--wait-seconds', type=int, default=0)
    gather.add_argument('--agent-result', action='append', default=[], metavar='ROLE=JSON_FILE')
    gather.add_argument('--agent-transcript', action='append', default=[], metavar='ROLE=JSONL_FILE')
    finish = sub.add_parser('finalize', help='Record acceptance, generate explicit update commands and a receipt.')
    finish.add_argument('run', type=Path)
    finish.add_argument('--judgments', type=Path, required=True)
    finish.add_argument('--claude-session', default='none')
    finish.add_argument('--new-claude-p', default='unknown')
    finish.add_argument('--monitoring-level', choices=('full', 'degraded', 'none', 'unknown'))
    args = parser.parse_args()
    try:
        if args.command == 'start':
            path, run = start(args.repo, args.host, args.role)
        elif args.command == 'collect':
            path = args.run
            entries = [value.split('=', 1) for value in args.agent_result]
            if any(len(entry) != 2 for entry in entries) or len(dict(entries)) != len(entries):
                raise ValueError('agent-result must contain distinct ROLE=JSON_FILE entries')
            transcripts = [value.split('=', 1) for value in args.agent_transcript]
            if any(len(entry) != 2 for entry in transcripts) or len(dict(transcripts)) != len(transcripts):
                raise ValueError('agent-transcript must contain distinct ROLE=JSONL_FILE entries')
            run = collect(path, args.wait_seconds, dict(entries), dict(transcripts))
        else:
            path = args.run
            run = finalize(path, json.loads(args.judgments.read_text()))
            run['receipt'] = make_receipt(path, run, args)
            save(path, run)
        print(json.dumps({'run': str(path.resolve()), **run}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, config.ConfigError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
