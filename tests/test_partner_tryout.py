from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "partner-tryout.py"
SPEC = importlib.util.spec_from_file_location("partner_tryout", SCRIPT)
partner_tryout = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = partner_tryout
SPEC.loader.exec_module(partner_tryout)

SORTED = '{"a":[2,1],"b":{"a":{"c":3},"z":1},"c":"x"}'


class FastWorkerAcceptanceTests(unittest.TestCase):
    def test_only_correct_raw_json_passes(self):
        for text in (SORTED, " \n" + json.dumps(json.loads(SORTED), indent=2) + "\n"):
            with self.subTest(text=text):
                result = partner_tryout.validate_fast_worker(text)
                self.assertTrue(result["passed"], result)
                self.assertTrue(result["format_valid"])
                self.assertTrue(result["content_valid"])
                self.assertTrue(result["keys_sorted"])

    def test_fences_remain_a_failure_even_when_contents_are_correct(self):
        result = partner_tryout.validate_fast_worker("```json\n" + SORTED + "\n```")
        self.assertFalse(result["passed"])
        self.assertFalse(result["format_valid"])
        self.assertTrue(result["content_valid"])
        self.assertTrue(result["keys_sorted"])

    def test_key_order_is_checked_at_every_depth(self):
        for text in (
            '{"c":"x","a":[2,1],"b":{"a":{"c":3},"z":1}}',
            '{"a":[2,1],"b":{"z":1,"a":{"c":3}},"c":"x"}',
        ):
            with self.subTest(text=text):
                result = partner_tryout.validate_fast_worker(text)
                self.assertTrue(result["content_valid"])
                self.assertFalse(result["keys_sorted"])
                self.assertFalse(result["passed"])

    def test_content_comparison_preserves_types_and_array_order(self):
        for text in (
            SORTED.replace('[2,1]', '[1,2]'),
            SORTED.replace('"z":1', '"z":true'),
            SORTED.replace('"c":3', '"c":4'),
            SORTED.replace('"c":"x"', '"c":"y"'),
            '[]', 'null',
        ):
            with self.subTest(text=text):
                result = partner_tryout.validate_fast_worker(text)
                self.assertFalse(result["content_valid"])
                self.assertFalse(result["passed"])

    def test_duplicate_keys_nonfinite_numbers_and_extra_text_are_invalid(self):
        for text in (
            SORTED.replace('"z":1', '"z":0,"z":1'),
            SORTED.replace('"c":3', '"c":3,"c":3'),
            SORTED.replace('"z":1', '"z":NaN'),
            SORTED.replace('"z":1', '"z":Infinity'),
            'Result: ' + SORTED, SORTED + '\nDone.', '',
        ):
            with self.subTest(text=text):
                result = partner_tryout.validate_fast_worker(text)
                self.assertFalse(result["format_valid"])
                self.assertFalse(result["passed"])


class TryoutWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.identities = {
            "fast_worker": {"backend": "codex", "model": "test-fast", "effort": "medium"},
            "deep_reasoner": {"backend": "claude", "model": "opus", "effort": "high"},
            "arbiter": {"backend": "codex", "model": "test-arbiter", "effort": "high"},
        }

    def start(self, fail=False):
        def delegate(args, **kwargs):
            self.assertEqual(args[0], "submit")
            self.assertIn("--read-only", args)
            self.assertNotIn("--wait", args)
            role = args[args.index("--role") + 1]
            self.assertEqual(args[args.index("--model") + 1], self.identities[role]["model"])
            self.assertEqual(args[args.index("--effort") + 1], self.identities[role]["effort"])
            if fail and role == "arbiter":
                raise RuntimeError("submission denied")
            return "job-" + role
        with patch.object(partner_tryout, "resolve_roles", return_value=("global", {
            role: {**value, "scope": "global"} for role, value in self.identities.items()
        })), patch.object(partner_tryout, "delegate", side_effect=delegate):
            return partner_tryout.start(self.repo, "claude_code", None)

    def test_fixed_tasks_use_config_and_start_independent_jobs_without_waiting(self):
        path, run = self.start()
        self.assertEqual(run["roles"]["fast_worker"]["job_id"], "job-fast_worker")
        self.assertEqual(run["roles"]["arbiter"]["job_id"], "job-arbiter")
        packet = run["roles"]["deep_reasoner"]["native_agent"]
        self.assertEqual(packet["model"], "opus")
        self.assertEqual(packet["effort"], "high")
        self.assertEqual(packet["prompt"], partner_tryout.task_prompt("arbiter"))
        self.assertNotIn("deep_reasoner", packet["prompt"])
        self.assertIn("Do not edit", packet["prompt"])
        self.assertEqual(json.loads(path.read_text()), run)

    def test_partial_submission_keeps_successful_ids_and_is_never_retried_by_collect(self):
        path, run = self.start(fail=True)
        self.assertEqual(run["roles"]["arbiter"]["state"], "submission_failed")
        self.assertEqual(run["roles"]["fast_worker"]["job_id"], "job-fast_worker")
        with patch.object(partner_tryout, "delegate", return_value="state: RUNNING\n") as call:
            result = partner_tryout.collect(path, 0, {})
        self.assertTrue(all(c.args[0][0] == "status" for c in call.call_args_list))
        self.assertEqual(result["roles"]["fast_worker"]["state"], "RUNNING")
        self.assertFalse(result["roles"]["fast_worker"].get("passed", False))

    def test_process_success_is_required_before_strict_acceptance(self):
        for state, rc in (("FAILED", 1), ("DONE", 0), ("DONE", None)):
            with self.subTest(state=state, rc=rc):
                path, _ = self.start()
                def delegate(args, **kwargs):
                    if args[0] == "status":
                        return "state: " + state + "\n"
                    return json.dumps({"agent_message": SORTED, "observed_models": [],
                        "execution": {"returncode": rc, "elapsed_seconds": 3.25}})
                with patch.object(partner_tryout, "delegate", side_effect=delegate):
                    run = partner_tryout.collect(path, 0, {})
                row = run["roles"]["fast_worker"]
                self.assertEqual(row["passed"], state == "DONE" and rc == 0)
                self.assertEqual(row["evidence"]["execution"]["elapsed_seconds"], 3.25)
                self.assertEqual(row["evidence"]["observed_models"], [])
                self.assertFalse(run["roles"]["arbiter"].get("passed", False))

    def test_native_completion_is_explicit_and_missing_timing_stays_unknown(self):
        path, _ = self.start()
        evidence = self.repo / "native.json"
        evidence.write_text(json.dumps({"agent_message": "A. It travels with the repo.",
            "completed": False, "source": "native Agent result"}))
        with patch.object(partner_tryout, "delegate", return_value="state: RUNNING\n"):
            run = partner_tryout.collect(path, 0, {"deep_reasoner": evidence})
        self.assertEqual(run["roles"]["deep_reasoner"]["state"], "RUNNING")
        self.assertIsNone(run["roles"]["deep_reasoner"]["evidence"]["execution"]["elapsed_seconds"])

    def test_missing_configuration_fails_before_any_dispatch(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.repo / "config")}), \
                patch.object(partner_tryout, "delegate") as dispatch:
            with self.assertRaisesRegex(ValueError, "not configured"):
                partner_tryout.start(self.repo, "claude_code", None)
        dispatch.assert_not_called()
        self.assertFalse((self.repo / ".partner").exists())

    def test_scope_follows_each_role_instead_of_top_overlay(self):
        global_path = self.repo / "config" / "partner" / "config.toml"
        global_path.parent.mkdir(parents=True)
        global_path.write_text('schema_version = 2\nrevision = 0\n' + partner_tryout.config.emit_host_sections(
            "claude_code", self.identities))
        project_path = self.repo / ".partner" / "config.toml"
        project_path.parent.mkdir()
        project_path.write_text('schema_version = 2\nrevision = 0\n' + partner_tryout.config.emit_host_sections(
            "claude_code", {"arbiter": self.identities["arbiter"]}))
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.repo / "config")}):
            source, roles = partner_tryout.resolve_roles(self.repo, "claude_code", None)
        self.assertEqual(source, "project")
        self.assertEqual(roles["fast_worker"]["scope"], "global")
        self.assertEqual(roles["arbiter"]["scope"], "project")

    def test_finalize_keeps_strict_failure_and_reports_pending_or_denied_writes(self):
        path, run = self.start()
        for role, row in run["roles"].items():
            row.update(state="DONE", process_succeeded=True, passed=False,
                verified=True, verified_at="2020-01-01T00:00:00Z",
                evidence={"agent_message": "A. It travels with the repo."})
        run["roles"]["fast_worker"]["validation"] = partner_tryout.validate_fast_worker(
            "```json\n" + SORTED + "\n```")
        partner_tryout.save(path, run)
        decisions = {
            role: {"accepted": True, "reason": "A travels on rename; independent answer",
                   "routing_established": True, "verification_write": "denied"}
            for role in run["roles"]}
        with patch.object(partner_tryout, "resolve_roles", return_value=("global", {
            role: {**row} for role, row in run["roles"].items()
        })):
            report = partner_tryout.finalize(path, decisions)
        self.assertFalse(report["roles"]["fast_worker"]["passed"])
        self.assertNotIn("verification_command", report["roles"]["fast_worker"])
        self.assertTrue(report["roles"]["deep_reasoner"]["passed"])
        self.assertFalse(report["roles"]["deep_reasoner"]["verified_this_run"])
        self.assertEqual(report["roles"]["deep_reasoner"]["verification_write"], "denied")
        self.assertIn("--scope global", report["roles"]["deep_reasoner"]["verification_command"])

    def test_absent_judgment_or_changed_route_never_marks_verified(self):
        path, run = self.start()
        run["roles"]["arbiter"].update(state="DONE", process_succeeded=True)
        partner_tryout.save(path, run)
        current = {role: {**row, "model": "changed"} for role, row in run["roles"].items()}
        with patch.object(partner_tryout, "resolve_roles", return_value=("global", current)):
            report = partner_tryout.finalize(path, {})
        self.assertFalse(report["roles"]["arbiter"]["passed"])
        self.assertFalse(report["roles"]["arbiter"]["verified_this_run"])
        self.assertNotIn("verification_command", report["roles"]["arbiter"])

    def test_interrupted_submission_can_collect_without_resubmitting_other_roles(self):
        path, run = self.start()
        for role, row in run["roles"].items():
            row.pop("job_id", None)
            row["state"] = "pending"
        run["roles"]["fast_worker"]["state"] = "submitting"
        (path.parent / 'fast_worker.submission').write_text('job-recovered')
        partner_tryout.save(path, run)
        with patch.object(partner_tryout, 'delegate', return_value='state: RUNNING\n'):
            result = partner_tryout.collect(path, 0, {})
        self.assertEqual(result['roles']['fast_worker']['job_id'], 'job-recovered')
        self.assertEqual(result['roles']['arbiter']['state'], 'pending')

    def test_initial_manifest_is_collectable_even_when_first_submission_interrupts(self):
        with patch.object(partner_tryout, 'resolve_roles', return_value=('global', self.identities)), \
                patch.object(partner_tryout, 'delegate', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                partner_tryout.start(self.repo, 'claude_code', None)
        path = next((self.repo / '.partner' / 'receipts').glob('tryout-*/run.json'))
        result = partner_tryout.collect(path, 0, {})
        self.assertEqual(result['roles']['arbiter']['state'], 'pending')

    def test_generated_receipt_passes_the_real_existing_schema(self):
        path, run = self.start()
        for row in run['roles'].values():
            row.update(passed=False, verified_this_run=False, verification_write='pending')
        args = SimpleNamespace(claude_session='none', new_claude_p='unknown', monitoring_level='unknown')
        receipt = partner_tryout.make_receipt(path, run, args)
        self.assertIn('[Partner session receipt]', Path(receipt).read_text())
        self.assertIn('verified', Path(receipt).read_text())


if __name__ == "__main__":
    unittest.main()
