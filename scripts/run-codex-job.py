#!/usr/bin/env python3
"""Run one delegated command with durable timing and an optional wall limit."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stop_group(process: subprocess.Popen) -> None:
    # The CLI can exit before its children; always clean up the whole group.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.poll()
        return
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            # Retry after poll() reaps a leader that exited just before the probe.
            pass
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--wall-timeout-seconds", type=positive_int)
    parser.add_argument("--write-lock", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if not args.job_dir.is_dir():
        parser.error("--job-dir must be an existing directory")
    if (args.job_dir / "execution.json").exists() or (args.job_dir / "exit_code").exists():
        parser.error("job already started; use a new job directory")

    cancelled = False

    def cancel(signum, frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    started = time.monotonic()
    metadata = {
        "started_at": utc_now(),
        "finished_at": None,
        "elapsed_seconds": None,
        "returncode": None,
        "failure_kind": None,
    }

    def save():
        temporary = args.job_dir / ".execution.json.tmp"
        temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.job_dir / "execution.json")

    save()
    process = None
    lock = None
    writer_busy = False
    returncode = 127
    failure_kind = "spawn_error"
    with (args.job_dir / "log.jsonl").open("wb") as stdout, \
            (args.job_dir / "stderr.log").open("wb") as stderr:
        try:
            if args.write_lock:
                lock = args.write_lock.open("a")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    writer_busy = True
                    returncode, failure_kind = 75, "writer_busy"
                    stderr.write(b"Another writer owns this workspace; wait or use a separate worktree.\n")
            if writer_busy:
                pass
            elif cancelled:
                returncode, failure_kind = 130, "cancelled"
            else:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=stderr, start_new_session=True)
                while True:
                    if cancelled:
                        returncode, failure_kind = 130, "cancelled"
                        break
                    if args.wall_timeout_seconds and time.monotonic() - started >= args.wall_timeout_seconds:
                        returncode, failure_kind = 124, "wall_timeout"
                        break
                    try:
                        child_code = process.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        continue
                    if cancelled:
                        returncode, failure_kind = 130, "cancelled"
                        break
                    returncode = child_code if child_code >= 0 else 128 - child_code
                    failure_kind = "process_exit" if returncode else None
                    break
        except OSError as error:
            stderr.write((str(error) + "\n").encode("utf-8"))
        finally:
            try:
                if process is not None:
                    stop_group(process)
            except (OSError, subprocess.TimeoutExpired) as error:
                stderr.write(("Process cleanup failed: " + str(error) + "\n").encode("utf-8"))
                returncode, failure_kind = 125, "process_exit"
            finally:
                if lock is not None:
                    lock.close()
    metadata.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - started, 6),
                    returncode=returncode, failure_kind=failure_kind)
    save()
    # Write the terminal marker last so status cannot race the final metadata.
    (args.job_dir / "exit_code").write_text(str(returncode) + "\n", encoding="utf-8")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
