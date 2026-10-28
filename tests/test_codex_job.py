from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-codex-job.py"


class CodexJobTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name) / "job"
        self.job.mkdir()

    def command(self, code, timeout=None, lock=None, job=None):
        args = [sys.executable, str(SCRIPT), "--job-dir", str(job or self.job)]
        if lock is not None:
            args.extend(("--write-lock", str(lock)))
        if timeout is not None:
            args.extend(("--wall-timeout-seconds", str(timeout)))
        return [*args, "--", sys.executable, "-c", code]

    def metadata(self):
        return json.loads((self.job / "execution.json").read_text())

    def wait_for(self, path):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.02)
        self.fail(f"child did not write {path}")

    def assert_stopped(self):
        heartbeat = self.job / "heartbeat"
        before = heartbeat.read_text()
        time.sleep(0.2)
        self.assertEqual(before, heartbeat.read_text(), "grandchild is still running")

    def spawn_grandchild_code(self, exit_parent=False):
        child = (
            "import signal,time\n"
            "from pathlib import Path\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"heartbeat = Path({str(self.job / 'heartbeat')!r})\n"
            "for i in range(1500):\n"
            " heartbeat.write_text(str(i)); time.sleep(0.02)\n"
        )
        return (
            "import subprocess, sys, time\n"
            "from pathlib import Path\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
            f"heartbeat = Path({str(self.job / 'heartbeat')!r})\n"
            "while not heartbeat.exists(): time.sleep(0.01)\n"
            f"Path({str(self.job / 'grandchild')!r}).write_text(str(child.pid))\n"
            + ("sys.exit(0)\n" if exit_parent else "time.sleep(30)\n")
        )

    def test_success_records_timing_logs_closed_stdin_and_inherited_cwd(self):
        result = subprocess.run(self.command(
            "import os,sys; print('stdin=' + sys.stdin.read()); print(os.getcwd()); "
            "print('diagnostic', file=sys.stderr)"), cwd=self.job, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(f"stdin=\n{self.job.resolve()}\n", (self.job / "log.jsonl").read_text())
        self.assertEqual("diagnostic\n", (self.job / "stderr.log").read_text())
        metadata = self.metadata()
        self.assertIsNone(metadata["failure_kind"])
        self.assertEqual(0, metadata["returncode"])
        self.assertGreaterEqual(metadata["elapsed_seconds"], 0)
        self.assertTrue(metadata["started_at"].endswith("Z"))
        self.assertTrue(metadata["finished_at"].endswith("Z"))
        self.assertEqual("0", (self.job / "exit_code").read_text().strip())

    def test_nonzero_child_exit_is_not_reported_as_success(self):
        result = subprocess.run(self.command("import sys; sys.exit(7)"), capture_output=True)
        self.assertEqual(7, result.returncode)
        self.assertEqual("process_exit", self.metadata()["failure_kind"])
        self.assertEqual(7, self.metadata()["returncode"])

    def test_timeout_terminates_the_child_process_group(self):
        started = time.monotonic()
        result = subprocess.run(self.command(self.spawn_grandchild_code(), timeout=1),
                                capture_output=True, text=True, timeout=6)
        self.assertEqual(124, result.returncode, result.stderr)
        self.assertEqual("wall_timeout", self.metadata()["failure_kind"])
        self.assertLess(time.monotonic() - started, 5)
        self.assert_stopped()

    def test_cancel_signal_reaches_children_and_records_cancelled(self):
        process = subprocess.Popen(self.command(self.spawn_grandchild_code()),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(self.job / "grandchild")
            process.send_signal(signal.SIGTERM)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(130, process.returncode, stderr)
            self.assertEqual("cancelled", self.metadata()["failure_kind"])
            self.assert_stopped()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.communicate()

    def test_successful_parent_cannot_leave_background_children(self):
        result = subprocess.run(self.command(self.spawn_grandchild_code(exit_parent=True)),
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_stopped()

    def test_spawn_failure_still_leaves_terminal_state(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--job-dir", str(self.job),
                                 "--", str(self.job / "missing-command")], capture_output=True)
        self.assertEqual(127, result.returncode)
        self.assertEqual("spawn_error", self.metadata()["failure_kind"])
        self.assertEqual("127", (self.job / "exit_code").read_text().strip())

    def test_same_workspace_rejects_a_second_writer_without_starting_it(self):
        self.check_writer_lock(shared=True)

    def test_independent_workspaces_can_run_writers_concurrently(self):
        self.check_writer_lock(shared=False)

    def check_writer_lock(self, shared):
        ready = self.job / "ready"
        lock = self.job.parent / "writer.lock"
        code = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(20)"
        process = subprocess.Popen(self.command(code, lock=lock),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.wait_for(ready)
            second = self.job.parent / "second"
            second.mkdir()
            second_lock = lock if shared else self.job.parent / "other.lock"
            result = subprocess.run(self.command("print('second ran')", lock=second_lock, job=second),
                                    capture_output=True, timeout=5)
            self.assertEqual(75 if shared else 0, result.returncode, result.stderr)
            metadata = json.loads((second / "execution.json").read_text())
            self.assertEqual("writer_busy" if shared else None, metadata["failure_kind"])
            self.assertEqual("" if shared else "second ran\n", (second / "log.jsonl").read_text())
            self.assertTrue(lock.exists())
        finally:
            process.terminate()
            process.communicate(timeout=5)

    def test_invalid_timeout_fails_before_launch(self):
        result = subprocess.run(self.command("print('should not run')", timeout=0), capture_output=True)
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.job / "execution.json").exists())


if __name__ == "__main__":
    unittest.main()
