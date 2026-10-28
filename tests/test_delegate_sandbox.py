from __future__ import annotations

import os
import json
import shlex
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/delegate-codex.sh")

# A job that finishes DONE having written nothing is the exact failure this
# suite guards: `codex exec` defaults to a read-only sandbox, so an
# implementation job submitted without --writable silently changes no files.
FAKE_CODEX = (
    "#!/usr/bin/env bash\n"
    "if [ \"${1:-}\" = \"--version\" ]; then printf 'codex-cli test-version\\n'; exit 0; fi\n"
    "printf '{\"session_id\": \"test-session-0001\"}\\n'\n"
)


class DelegateSandboxTests(unittest.TestCase):
    def workspace(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", str(repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        prompt = root / "prompt.md"
        prompt.write_text("test prompt\n", encoding="utf-8")
        fake_codex = root / "codex"
        fake_codex.write_text(FAKE_CODEX, encoding="utf-8")
        fake_codex.chmod(0o755)
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "xdg"),
                "PARTNER_CODEX_BIN": str(fake_codex),
            }
        )
        return root, repo, prompt, fake_codex, env

    def run_script(self, env, *arguments):
        return subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def submit(self, env, repo, prompt, *arguments):
        result = self.run_script(
            env,
            "submit",
            "--repo",
            str(repo),
            "--prompt-file",
            str(prompt),
            *arguments,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        job_id = result.stdout.strip().splitlines()[-1]
        job = repo / ".partner" / "jobs" / job_id
        for _ in range(50):
            if (job / "exit_code").exists():
                break
            time.sleep(0.1)
        return job_id, job

    @staticmethod
    def parsed(output: str) -> dict[str, str]:
        return dict(line.split("=", 1) for line in output.splitlines())

    def dry_run(self, *arguments):
        _, repo, prompt, _, env = self.workspace()
        result = self.run_script(
            env,
            "submit",
            "--repo",
            str(repo),
            "--prompt-file",
            str(prompt),
            "--dry-run",
            *arguments,
        )
        return result

    def test_dry_run_reports_codex_default_sandbox_without_flags(self):
        result = self.dry_run()
        self.assertEqual((0, ""), (result.returncode, result.stderr))
        self.assertEqual("codex-default", self.parsed(result.stdout)["sandbox"])

    def test_dry_run_reports_workspace_write_for_writable(self):
        result = self.dry_run("--writable")
        self.assertEqual((0, ""), (result.returncode, result.stderr))
        self.assertEqual("workspace-write", self.parsed(result.stdout)["sandbox"])

    def test_dry_run_reports_read_only(self):
        result = self.dry_run("--read-only")
        self.assertEqual((0, ""), (result.returncode, result.stderr))
        self.assertEqual("read-only", self.parsed(result.stdout)["sandbox"])

    def test_read_only_and_writable_are_mutually_exclusive(self):
        result = self.dry_run("--read-only", "--writable")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("mutually exclusive", result.stderr)

    def test_submit_without_flags_passes_no_sandbox_flag(self):
        _, repo, prompt, _, env = self.workspace()
        _, job = self.submit(env, repo, prompt)
        run_script = (job / "run.sh").read_text(encoding="utf-8")
        self.assertNotIn("-s workspace-write", run_script)
        self.assertNotIn("-s read-only", run_script)

    def test_submit_writable_passes_workspace_write(self):
        _, repo, prompt, _, env = self.workspace()
        _, job = self.submit(env, repo, prompt, "--writable")
        self.assertIn("-s workspace-write", (job / "run.sh").read_text(encoding="utf-8"))
        self.assertIn("sandbox=workspace-write", (job / "meta").read_text(encoding="utf-8"))

    def test_submit_read_only_still_passes_read_only(self):
        _, repo, prompt, _, env = self.workspace()
        _, job = self.submit(env, repo, prompt, "--read-only")
        self.assertIn("-s read-only", (job / "run.sh").read_text(encoding="utf-8"))

    def test_resume_writable_uses_config_override(self):
        # `codex exec resume` rejects -s, so the sandbox has to ride on -c.
        _, repo, prompt, _, env = self.workspace()
        parent_id, _ = self.submit(env, repo, prompt)
        result = self.run_script(
            env,
            "resume",
            parent_id,
            "--repo",
            str(repo),
            "--prompt-file",
            str(prompt),
            "--writable",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        job = repo / ".partner" / "jobs" / result.stdout.strip().splitlines()[-1]
        run_script = (job / "run.sh").read_text(encoding="utf-8")
        self.assertIn('sandbox_mode="workspace-write"', shlex.split(run_script.splitlines()[-1]))
        self.assertNotIn("-s workspace-write", run_script)

    def test_resume_keeps_explicit_parent_sandbox_and_requested_model(self):
        for flag, sandbox in (("--read-only", "read-only"), ("--writable", "workspace-write")):
            with self.subTest(sandbox=sandbox):
                _, repo, prompt, _, env = self.workspace()
                parent, _ = self.submit(env, repo, prompt, flag, "--model", "gpt-test")
                result = self.run_script(env, "resume", parent, "--repo", str(repo), "--prompt-file", str(prompt))
                self.assertEqual(0, result.returncode, result.stderr)
                job = repo / ".partner/jobs" / result.stdout.strip()
                args = shlex.split((job / "run.sh").read_text().splitlines()[-1])
                self.assertIn(f'sandbox_mode="{sandbox}"', args)
                meta = self.parsed((job / "meta").read_text())
                self.assertEqual(sandbox, meta["sandbox"])
                self.assertEqual("gpt-test", meta["requested_model"])
                for _ in range(50):
                    if (job / "exit_code").exists():
                        break
                    time.sleep(0.1)

    def test_cancelled_runner_cannot_resume_until_cleanup_finishes(self):
        _, repo, prompt, _, env = self.workspace()
        job = repo / ".partner/jobs/job-cancelling"
        job.mkdir(parents=True)
        (job / "meta").write_text("runner_managed=true\n")
        (job / "pid").write_text(str(os.getpid()))
        (job / "cancelled").touch()
        result = self.run_script(env, "resume", job.name, "--repo", str(repo), "--prompt-file", str(prompt))
        self.assertNotEqual(0, result.returncode)
        self.assertIn("parent job still running", result.stderr)
        (job / "exit_code").write_text("130\n")
        result = self.run_script(env, "status", job.name, "--repo", str(repo))
        self.assertIn("state: CANCELLED", result.stdout)

    def test_result_separates_process_completion_from_acceptance(self):
        _, repo, prompt, _, env = self.workspace()
        job_id, _ = self.submit(env, repo, prompt, "--model", "gpt-test")
        result = self.run_script(env, "result", job_id, "--repo", str(repo), "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("pending", report["acceptance"])
        self.assertEqual("unknown", report["billing_source"])
        self.assertEqual([], report["observed_models"])
        self.assertEqual("gpt-test", report["requested_model"])
        self.assertEqual(0, report["execution"]["returncode"])
        self.assertGreaterEqual(report["execution"]["elapsed_seconds"], 0)

    def test_job_wall_timeout_is_enforced_without_a_polling_host(self):
        _, repo, prompt, codex, env = self.workspace()
        codex.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo fake; exit; fi\nsleep 30\n')
        job_id, job = self.submit(env, repo, prompt, "--wall-timeout", "1")
        self.assertEqual("124", (job / "exit_code").read_text().strip())
        self.assertEqual("wall_timeout", json.loads((job / "execution.json").read_text())["failure_kind"])
        result = self.run_script(env, "status", job_id, "--repo", str(repo))
        self.assertNotEqual(0, result.returncode)

    def test_resume_prefers_explicit_partner_codex_bin_over_parent(self):
        # Inheriting the parent binary unconditionally made PARTNER_CODEX_BIN
        # silently inert on resume, so a wrapper CLI never ran.
        root, repo, prompt, _, env = self.workspace()
        parent_id, _ = self.submit(env, repo, prompt)
        override = root / "codex-override"
        override.write_text(FAKE_CODEX, encoding="utf-8")
        override.chmod(0o755)
        env = dict(env, PARTNER_CODEX_BIN=str(override))
        result = self.run_script(
            env,
            "resume",
            parent_id,
            "--repo",
            str(repo),
            "--prompt-file",
            str(prompt),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        job = repo / ".partner" / "jobs" / result.stdout.strip().splitlines()[-1]
        meta = self.parsed((job / "meta").read_text(encoding="utf-8"))
        self.assertEqual(str(override), meta["codex_bin"])
        self.assertEqual("env", meta["codex_bin_source"])

    def test_resume_falls_back_to_parent_binary_without_override(self):
        _, repo, prompt, fake_codex, env = self.workspace()
        parent_id, _ = self.submit(env, repo, prompt)
        env = {key: value for key, value in env.items() if key != "PARTNER_CODEX_BIN"}
        result = self.run_script(
            env,
            "resume",
            parent_id,
            "--repo",
            str(repo),
            "--prompt-file",
            str(prompt),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        job = repo / ".partner" / "jobs" / result.stdout.strip().splitlines()[-1]
        meta = self.parsed((job / "meta").read_text(encoding="utf-8"))
        self.assertEqual(str(fake_codex), meta["codex_bin"])
        self.assertEqual("parent", meta["codex_bin_source"])


if __name__ == "__main__":
    unittest.main()
