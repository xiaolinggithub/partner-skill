from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import subprocess
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

    def test_fences_require_explicit_opt_in_and_record_accepted_format(self):
        for opening in ("```", "```json"):
            text = opening + "\n" + SORTED + "\n```"
            for enabled in (False, True):
                with self.subTest(opening=opening, enabled=enabled):
                    result = partner_tryout.validate_fast_worker(text, allow_fences=enabled)
                    self.assertEqual(result["passed"], enabled)
                    self.assertEqual(result["format_valid"], enabled)
                    self.assertEqual(result.get("fence_accepted", False), enabled)
                    self.assertEqual(result["errors"], [] if enabled else ["markdown_fence"])
        result = partner_tryout.validate_fast_worker(SORTED, allow_fences=True)
        self.assertTrue(result["passed"])
        self.assertNotIn("fence_accepted", result)

    def test_key_order_is_checked_at_every_depth(self):
        for text in (
            '{"c":"x","a":[2,1],"b":{"a":{"c":3},"z":1}}',
            '{"a":[2,1],"b":{"z":1,"a":{"c":3}},"c":"x"}',
        ):
            for enabled in (False, True):
                with self.subTest(text=text, enabled=enabled):
                    candidate = "```json\n" + text + "\n```" if enabled else text
                    result = partner_tryout.validate_fast_worker(candidate, allow_fences=enabled)
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
            for enabled in (False, True):
                with self.subTest(text=text, enabled=enabled):
                    candidate = "```json\n" + text + "\n```" if enabled else text
                    result = partner_tryout.validate_fast_worker(candidate, allow_fences=enabled)
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
            for enabled in (False, True):
                with self.subTest(text=text, enabled=enabled):
                    candidate = "```json\n" + text + "\n```" if enabled else text
                    result = partner_tryout.validate_fast_worker(candidate, allow_fences=enabled)
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

    def start(self, fail=False, expected_models=None):
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
            return partner_tryout.start(self.repo, "claude_code", None, expected_models)

    def batch(self, args, state='RUNNING', evidence=None):
        self.assertEqual(args[0], 'collect')
        ids = args[1:args.index('--repo')]
        return json.dumps({'jobs': [dict(job_id=job, state=state,
            **({'result': evidence} if evidence is not None else {})) for job in ids],
            'timed_out': False})

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
        with patch.object(partner_tryout, "delegate", side_effect=self.batch) as call:
            result = partner_tryout.collect(path, 0, {})
        self.assertTrue(all(c.args[0][0] == "collect" for c in call.call_args_list))
        self.assertEqual(result["roles"]["fast_worker"]["state"], "RUNNING")
        self.assertFalse(result["roles"]["fast_worker"].get("passed", False))

    def test_process_success_is_required_before_strict_acceptance(self):
        for state, rc in (("FAILED", 1), ("DONE", 0), ("DONE", None)):
            with self.subTest(state=state, rc=rc):
                path, _ = self.start()
                def delegate(args, **kwargs):
                    return self.batch(args, state, {"agent_message": SORTED, "observed_models": [],
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
        with patch.object(partner_tryout, "delegate", side_effect=self.batch):
            run = partner_tryout.collect(path, 0, {"deep_reasoner": evidence})
        self.assertEqual(run["roles"]["deep_reasoner"]["state"], "RUNNING")
        self.assertIsNone(run["roles"]["deep_reasoner"]["evidence"]["execution"]["elapsed_seconds"])

    def test_collect_uses_snapshotted_fence_policy_and_only_true_opts_in(self):
        evidence = {"agent_message": "```json\n" + SORTED + "\n```",
            "completed": True, "source": "native Agent result",
            "execution": {"returncode": 0}}
        native = self.repo / "native.json"
        native.write_text(json.dumps(evidence))
        for backend in ("codex", "claude"):
            for value in (None, False, True, "false", 1, [False]):
                with self.subTest(backend=backend, value=value):
                    identity = self.identities["fast_worker"]
                    identity["backend"] = backend
                    identity.pop("accept_fenced_json", None)
                    if value is not None:
                        identity["accept_fenced_json"] = value
                    path, run = self.start()
                    self.assertEqual(run["roles"]["fast_worker"].get("accept_fenced_json"), value)
                    identity["accept_fenced_json"] = value is not True
                    def delegate(args, **kwargs):
                        return self.batch(args, 'DONE', evidence)
                    with patch.object(partner_tryout, "delegate", side_effect=delegate):
                        run = partner_tryout.collect(path, 0, {"fast_worker": native} if backend == "claude" else {})
                    row = run["roles"]["fast_worker"]
                    self.assertEqual(row["passed"], value is True)
                    self.assertEqual(row["validation"].get("fence_accepted", False), value is True)
                    self.assertEqual(row["evidence"]["agent_message"], evidence["agent_message"])

    def native_rows(self):
        return [
            {'type': 'user', 'timestamp': '2026-10-28T00:00:00Z',
             'message': {'content': partner_tryout.task_prompt('deep_reasoner')}},
            {'type': 'api-request', 'model': 'requested-opus',
             'message': {'model': 'requested-opus'}},
            {'type': 'assistant', 'timestamp': '2026-10-28T00:00:02Z',
             'message': {'model': 'actual-model', 'content': [{'type': 'tool_use',
                 'name': 'SubagentHandback', 'id': 'handback-1',
                 'input': {'message': 'A. It travels with the repo.'}}]}},
            {'type': 'user', 'timestamp': '2026-10-28T00:00:03Z',
             'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'handback-1',
                 'content': [{'type': 'text', 'text': '{"success":true}'}]}]}},
        ]

    def test_native_transcript_extracts_only_observed_models_and_confirmed_completion(self):
        path, _ = self.start()
        native = self.repo / 'native.jsonl'
        native.write_text('\n'.join(json.dumps(row) for row in self.native_rows()))
        with patch.object(partner_tryout, 'delegate', side_effect=self.batch):
            run = partner_tryout.collect(path, 0, {}, {'deep_reasoner': native})
        row = run['roles']['deep_reasoner']
        self.assertTrue(row['process_succeeded'])
        self.assertFalse(row['passed'])  # Reasoning still needs the driver's judgment.
        self.assertEqual(row['evidence']['agent_message'], 'A. It travels with the repo.')
        self.assertEqual(row['evidence']['observed_models'], ['actual-model'])
        self.assertEqual(row['evidence']['execution']['elapsed_seconds'], 3)

    def test_native_transcript_cannot_promote_partial_failed_or_unrelated_evidence(self):
        native = self.repo / 'native.jsonl'
        for variant in ('partial', 'failed', 'wrong_id', 'is_error'):
            with self.subTest(variant=variant):
                rows = self.native_rows()
                result = rows[-1]['message']['content'][0]
                if variant == 'partial':
                    rows.pop()
                elif variant == 'failed':
                    result['content'][0]['text'] = '{"success":false}'
                elif variant == 'wrong_id':
                    result['tool_use_id'] = 'unrelated'
                else:
                    result['is_error'] = True
                native.write_text('\n'.join(json.dumps(row) for row in rows))
                evidence = partner_tryout.native_transcript(native, 'deep_reasoner')
                self.assertFalse(evidence['completed'])
                self.assertIsNone(evidence['execution']['returncode'])
        rows = self.native_rows()
        rows[0]['message']['content'] = 'An unrelated task'
        native.write_text('\n'.join(json.dumps(row) for row in rows))
        with self.assertRaisesRegex(ValueError, 'exact task'):
            partner_tryout.native_transcript(native, 'deep_reasoner')

    def test_native_transcript_missing_timestamps_stays_unknown(self):
        native = self.repo / 'native.jsonl'
        rows = self.native_rows()
        rows[-1].pop('timestamp')
        native.write_text('\n'.join(json.dumps(row) for row in rows))
        evidence = partner_tryout.native_transcript(native, 'deep_reasoner')
        self.assertTrue(evidence['completed'])
        self.assertIsNone(evidence['execution']['elapsed_seconds'])

    def test_new_handback_cannot_reuse_an_older_answer_success_or_timing(self):
        native = self.repo / 'native.jsonl'
        rows = self.native_rows()
        rows.append({'type': 'assistant', 'message': {'model': 'actual-model',
            'content': [{'type': 'tool_use', 'name': 'SubagentHandback', 'id': 'handback-2',
                'input': {'message': 'Unconfirmed new answer'}}]}})
        native.write_text('\n'.join(json.dumps(row) for row in rows))
        evidence = partner_tryout.native_transcript(native, 'deep_reasoner')
        self.assertEqual(evidence['agent_message'], 'Unconfirmed new answer')
        self.assertFalse(evidence['completed'])
        self.assertEqual(evidence['execution'], {'returncode': None, 'elapsed_seconds': None})

    def test_native_transcript_cannot_replace_codex_or_conflict_with_another_source(self):
        path, _ = self.start()
        for results, transcripts in (({}, {'fast_worker': 'unused'}),
                                     ({'deep_reasoner': 'one'}, {'deep_reasoner': 'two'})):
            with self.subTest(results=results, transcripts=transcripts):
                with self.assertRaises(ValueError):
                    partner_tryout.collect(path, 0, results, transcripts)

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
            row.pop('routing_policy')  # Legacy receipts keep their original manual routing contract.
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
        self.assertNotIn("verification_command", report["roles"]["deep_reasoner"])

    def test_denial_clears_stale_commands_and_survives_later_finalize(self):
        for scope in ('project', 'global'):
            with self.subTest(scope=scope):
                path, run = self.start()
                for row in run['roles'].values():
                    row.update(scope=scope, state='DONE', process_succeeded=True,
                        validation={'passed': True}, evidence={'completed': True,
                        'source': 'native result', 'execution': {'returncode': 0}})
                partner_tryout.save(path, run)
                decisions = {role: {'accepted': True, 'reason': 'Meets the task'}
                             for role in run['roles']}
                with patch.object(partner_tryout, 'resolve_roles', return_value=(scope, run['roles'])):
                    pending = partner_tryout.finalize(path, decisions)
                    for row in pending['roles'].values():
                        self.assertIn('--scope ' + scope, row['verification_command'])
                    denied = {role: {**value, 'verification_write': 'denied'}
                              for role, value in decisions.items()}
                    partner_tryout.finalize(path, denied)
                    result = partner_tryout.finalize(path, decisions)
                for row in result['roles'].values():
                    self.assertTrue(row['passed'])
                    self.assertEqual(row['verification_write'], 'denied')
                    self.assertNotIn('verification_command', row)
                    self.assertFalse(row['verified_this_run'])
                self.assertEqual(json.loads(path.read_text()), result)

    def test_denial_is_not_replaced_by_confirmation_or_content_failure(self):
        path, run = self.start()
        for row in run['roles'].values():
            row.update(state='DONE', process_succeeded=True, validation={'passed': True},
                verified=True, verified_at=partner_tryout.utc_now(),
                evidence={'completed': True, 'source': 'native result', 'execution': {'returncode': 0}})
        partner_tryout.save(path, run)
        decisions = {role: {'accepted': role != 'arbiter', 'reason': 'Content reviewed',
                           'verification_write': 'denied'} for role in run['roles']}
        with patch.object(partner_tryout, 'resolve_roles', return_value=('global', run['roles'])):
            result = partner_tryout.finalize(path, decisions)
        for row in result['roles'].values():
            self.assertEqual(row['verification_write'], 'denied')
            self.assertNotIn('verification_command', row)
            self.assertFalse(row['verified_this_run'])

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

    def test_authorized_route_mapping_can_verify_without_matching_request_alias(self):
        path, run = self.start()
        run["roles"]["deep_reasoner"].update(state="DONE", process_succeeded=True,
            evidence={"observed_models": ["glm-5.3-flash"], "completed": True,
                      "source": "native result", "execution": {"returncode": 0}})
        partner_tryout.save(path, run)
        for established in (False, True):
            with self.subTest(established=established):
                decisions = {"deep_reasoner": {"accepted": True,
                    "reason": "Answer meets the task; dispatched via the user-authorized CC Switch route",
                    "routing_established": established}}
                with patch.object(partner_tryout, "resolve_roles", return_value=("global", run["roles"])):
                    report = partner_tryout.finalize(path, decisions)
                row = report["roles"]["deep_reasoner"]
                self.assertTrue(row["passed"])
                self.assertIn("verification_command", row)
                self.assertTrue(row['routing_established'])
                self.assertFalse(row["verified_this_run"])
                self.assertEqual(row["model"], "opus")
                self.assertEqual(row["evidence"]["observed_models"], ["glm-5.3-flash"])

    def test_start_rejects_partner_storage_before_config_or_dispatch(self):
        for repo in (self.repo / '.partner', self.repo / '.partner' / 'receipts'):
            with self.subTest(repo=repo), patch.object(partner_tryout, 'resolve_roles') as resolve:
                with self.assertRaisesRegex(ValueError, 'working project directory'):
                    partner_tryout.start(repo, 'claude_code', None)
                resolve.assert_not_called()
                self.assertFalse(repo.exists())

    def test_invalid_model_requirements_fail_before_dispatch(self):
        for expected in ({'unknown': 'opus'}, {'deep_reasoner': ''}):
            with self.subTest(expected=expected), patch.object(partner_tryout, 'resolve_roles',
                    return_value=('global', self.identities)), patch.object(partner_tryout, 'delegate') as dispatch:
                with self.assertRaisesRegex(ValueError, 'selected role'):
                    partner_tryout.start(self.repo, 'claude_code', None, expected)
                dispatch.assert_not_called()
                self.assertFalse((self.repo / '.partner').exists())

    def test_collected_route_policy_controls_verification_and_report(self):
        for expected, observed, completed, allowed in (
                (None, ['glm-5.3-flash'], True, True),
                (None, ['claude-opus'], True, True),
                (None, [], True, True),
                ('claude-opus', ['glm-5.3-flash'], True, False),
                ('claude-opus', [], True, False),
                ('claude-opus', ['claude-opus'], True, True),
                (None, ['glm-5.3-flash'], False, False)):
            with self.subTest(expected=expected, observed=observed, completed=completed):
                path, initial = self.start(expected_models={'deep_reasoner': expected} if expected else None)
                native = self.repo / 'route-result.json'
                native.write_text(json.dumps({'completed': completed, 'source': 'native result',
                    'agent_message': 'A. It travels with the repo.', 'observed_models': observed,
                    'execution': {'returncode': 0 if completed else None}}))
                with patch.object(partner_tryout, 'delegate', side_effect=self.batch):
                    partner_tryout.collect(path, 0, {'deep_reasoner': native})
                # Reproduce the wrong manual verdict from the live conversation, in both directions.
                decisions = {'deep_reasoner': {'accepted': True, 'reason': 'A travels on rename',
                    'routing_established': not allowed}}
                with patch.object(partner_tryout, 'resolve_roles', return_value=('global', initial['roles'])):
                    result = partner_tryout.finalize(path, decisions)
                row = result['roles']['deep_reasoner']
                self.assertEqual(row['routing_established'], allowed)
                self.assertEqual('verification_command' in row, allowed)
                self.assertEqual(row['evidence']['observed_models'], observed)
                self.assertFalse(row['verified_this_run'])
                self.assertIn('deep_reasoner: verification_write=', result['summary']['anomalies'])
                args = SimpleNamespace(claude_session='none', new_claude_p='unknown', monitoring_level='none')
                receipt = Path(partner_tryout.make_receipt(path, result, args)).read_text()
                self.assertIn('anomalies: ' + result['summary']['anomalies'], receipt)
                self.assertIn('anomalies: ' + result['summary']['anomalies'], result['report'])
                if allowed:
                    initial['roles']['deep_reasoner'].update(verified=True, verified_at=partner_tryout.utc_now())
                    with patch.object(partner_tryout, 'resolve_roles', return_value=('global', initial['roles'])):
                        confirmed = partner_tryout.finalize(path, decisions)
                    self.assertTrue(confirmed['roles']['deep_reasoner']['verified_this_run'])
                    self.assertNotIn('deep_reasoner:', confirmed['summary']['anomalies'])

    def test_route_cannot_verify_without_dispatch_or_after_config_change(self):
        for variant in ('no_dispatch', 'changed_config', 'unknown_policy'):
            with self.subTest(variant=variant):
                path, run = self.start()
                row = run['roles']['deep_reasoner']
                row.update(state='DONE', process_succeeded=True, evidence={'completed': True,
                    'source': 'native result', 'execution': {'returncode': 0}})
                current = {role: dict(value) for role, value in run['roles'].items()}
                if variant == 'no_dispatch':
                    row.pop('native_agent')
                elif variant == 'changed_config':
                    current['deep_reasoner']['model'] = 'changed'
                else:
                    row['routing_policy'] = {'mode': 'typo'}
                partner_tryout.save(path, run)
                with patch.object(partner_tryout, 'resolve_roles', return_value=('global', current)):
                    result = partner_tryout.finalize(path, {'deep_reasoner': {
                        'accepted': True, 'reason': 'valid answer', 'routing_established': True}})
                self.assertFalse(result['roles']['deep_reasoner']['routing_established'])
                self.assertNotIn('verification_command', result['roles']['deep_reasoner'])

    def test_codex_completion_uses_same_policy_and_unknown_model_stays_unknown(self):
        for expected in (None, 'required-model'):
            with self.subTest(expected=expected):
                path, initial = self.start(expected_models={'arbiter': expected} if expected else None)
                evidence = {'agent_message': 'A. It travels with the repo.',
                            'observed_models': [], 'execution': {'returncode': 0}}
                with patch.object(partner_tryout, 'delegate', side_effect=lambda args, **kw:
                        self.batch(args, 'DONE', evidence)):
                    partner_tryout.collect(path, 0, {})
                with patch.object(partner_tryout, 'resolve_roles', return_value=('global', initial['roles'])):
                    result = partner_tryout.finalize(path, {'arbiter': {
                        'accepted': True, 'reason': 'Independent answer addresses moved directories'}})
                row = result['roles']['arbiter']
                self.assertEqual(row['routing_established'], expected is None)
                self.assertEqual('verification_command' in row, expected is None)
                self.assertIn('observed=unknown', result['report'])

    def test_invalid_policy_cannot_fall_back_to_legacy_manual_verdict(self):
        for policy in (None, 'follow_current', {'mode': 'exact_model', 'expected_model': ''}):
            with self.subTest(policy=policy):
                row = {'routing_policy': policy, 'backend': 'codex', 'job_id': 'job-test',
                       'state': 'DONE', 'evidence': {'execution': {'returncode': 0}}}
                established, _ = partner_tryout.routing_result(row, True, {'routing_established': True})
                self.assertFalse(established)

    def test_interrupted_submission_can_collect_without_resubmitting_other_roles(self):
        path, run = self.start()
        for role, row in run["roles"].items():
            row.pop("job_id", None)
            row["state"] = "pending"
        run["roles"]["fast_worker"]["state"] = "submitting"
        (path.parent / 'fast_worker.submission').write_text('job-recovered')
        partner_tryout.save(path, run)
        with patch.object(partner_tryout, 'delegate', side_effect=self.batch):
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

    def prepared_verification(self):
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.repo / 'xdg')})
        env.start()
        self.addCleanup(env.stop)
        global_path = partner_tryout.config.global_config_path()
        project_path = partner_tryout.config.project_config_path(self.repo)
        partner_tryout.config.write_host_config(global_path, 'claude_code', {
            'fast_worker': self.identities['fast_worker']})
        partner_tryout.config.write_host_config(project_path, 'claude_code', {
            role: self.identities[role] for role in ('deep_reasoner', 'arbiter')})
        path, run = self.start()
        for role, row in run['roles'].items():
            row.update(scope='global' if role == 'fast_worker' else 'project',
                state='DONE', process_succeeded=True, validation={'passed': True},
                evidence={'completed': True, 'source': 'native test evidence',
                          'execution': {'returncode': 0}})
        partner_tryout.save(path, run)
        decisions = {role: {'accepted': True, 'reason': 'Meets original task',
                           'verification_write': 'pending'} for role in run['roles']}
        return path, decisions, global_path, project_path

    def test_apply_writes_each_real_scope_and_repeated_close_is_idempotent(self):
        path, decisions, global_path, project_path = self.prepared_verification()
        report = partner_tryout.finalize(path, decisions, apply_verification=True)
        for row in report['roles'].values():
            self.assertTrue(row['verified_this_run'])
            self.assertEqual(row['verification_write'], 'confirmed')
            self.assertNotIn('verification_command', row)
        before = [p.read_bytes() for p in (global_path, project_path)]
        with patch.object(partner_tryout.subprocess, 'run') as write:
            again = partner_tryout.finalize(path, decisions, apply_verification=True)
        write.assert_not_called()
        self.assertEqual(before, [p.read_bytes() for p in (global_path, project_path)])
        self.assertEqual(again['summary']['anomalies'], 'none')

    def test_default_finalize_still_only_proposes_writes(self):
        path, decisions, global_path, project_path = self.prepared_verification()
        before = [p.read_bytes() for p in (global_path, project_path)]
        with patch.object(partner_tryout.subprocess, 'run') as write:
            report = partner_tryout.finalize(path, decisions)
        write.assert_not_called()
        self.assertEqual(before, [p.read_bytes() for p in (global_path, project_path)])
        self.assertTrue(all('verification_command' in r for r in report['roles'].values()))

    def test_apply_preserves_partial_success_denial_and_other_write_errors(self):
        path, decisions, _, _ = self.prepared_verification()
        real_run = subprocess.run
        attempted = []
        def write(command, **kwargs):
            role = command[command.index('--role') + 1]
            attempted.append(role)
            if role == 'fast_worker':
                return subprocess.CompletedProcess(command, 1, '', 'PermissionError: permission denied')
            if role == 'deep_reasoner':
                return subprocess.CompletedProcess(command, 2, '', 'configuration lock timeout')
            return real_run(command, **kwargs)
        with patch.object(partner_tryout.subprocess, 'run', side_effect=write):
            report = partner_tryout.finalize(path, decisions, apply_verification=True)
        self.assertEqual(attempted, list(self.identities))
        rows = report['roles']
        self.assertEqual(rows['fast_worker']['verification_write'], 'denied')
        self.assertNotIn('verification_command', rows['fast_worker'])
        self.assertEqual(rows['deep_reasoner']['verification_write'], 'pending')
        self.assertIn('lock timeout', report['summary']['anomalies'])
        self.assertEqual(rows['arbiter']['verification_write'], 'confirmed')
        # Explicitly denying the remaining failed role permits no retry of any role.
        decisions['deep_reasoner']['verification_write'] = 'denied'
        with patch.object(partner_tryout.subprocess, 'run') as write_again:
            again = partner_tryout.finalize(path, decisions, apply_verification=True)
        write_again.assert_not_called()
        self.assertEqual(again['roles']['fast_worker']['verification_write'], 'denied')

    def test_multiline_write_failure_keeps_full_evidence_and_valid_receipt(self):
        path, decisions, _, _ = self.prepared_verification()
        error = 'Traceback (most recent call last):\n  config.py write\nPermissionError: [Errno 13] Permission denied'
        with patch.object(partner_tryout.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 1, '', error)):
            report = partner_tryout.finalize(path, decisions, apply_verification=True)
        self.assertEqual(report['roles']['fast_worker']['verification_error'], error)
        self.assertNotIn('\n', report['summary']['anomalies'])
        args = SimpleNamespace(claude_session='none', new_claude_p='unknown', monitoring_level='none')
        receipt = partner_tryout.make_receipt(path, report, args)
        result = subprocess.run([sys.executable, str(SCRIPT.parent / 'validate-receipt.py'), receipt],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_apply_rechecks_routing_between_writes(self):
        path, decisions, _, project_path = self.prepared_verification()
        real_run = subprocess.run
        attempted = []
        def write(command, **kwargs):
            role = command[command.index('--role') + 1]
            attempted.append(role)
            result = real_run(command, **kwargs)
            if role == 'fast_worker':
                partner_tryout.config.write_host_config(project_path, 'claude_code', {
                    'deep_reasoner': self.identities['deep_reasoner'],
                    'arbiter': {**self.identities['arbiter'], 'model': 'changed-route'}})
            return result
        with patch.object(partner_tryout.subprocess, 'run', side_effect=write):
            report = partner_tryout.finalize(path, decisions, apply_verification=True)
        self.assertEqual(attempted, ['fast_worker', 'deep_reasoner'])
        self.assertFalse(report['roles']['arbiter']['verified_this_run'])
        self.assertFalse(report['roles']['arbiter']['routing_unchanged'])
        self.assertNotIn('verification_command', report['roles']['arbiter'])

    def test_identity_change_at_write_boundary_cannot_verify_untested_model(self):
        path, decisions, global_path, _ = self.prepared_verification()
        real_run = subprocess.run
        def write(command, **kwargs):
            if command[command.index('--role') + 1] == 'fast_worker':
                partner_tryout.config.write_host_config(global_path, 'claude_code', {
                    'fast_worker': {**self.identities['fast_worker'], 'model': 'untested-new-model'}})
            return real_run(command, **kwargs)
        with patch.object(partner_tryout.subprocess, 'run', side_effect=write):
            report = partner_tryout.finalize(path, decisions, apply_verification=True)
        live = partner_tryout.resolve_roles(self.repo, 'claude_code', 'fast_worker')[1]['fast_worker']
        self.assertEqual(live['model'], 'untested-new-model')
        self.assertIsNot(live.get('verified'), True)
        self.assertFalse(report['roles']['fast_worker']['verified_this_run'])
        self.assertIn('changed before verification', report['roles']['fast_worker']['verification_error'])

    def test_successful_exit_without_readback_is_not_confirmation(self):
        path, decisions, _, _ = self.prepared_verification()
        with patch.object(partner_tryout.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, '', '')) as write:
            report = partner_tryout.finalize(path, decisions, apply_verification=True)
        self.assertEqual(write.call_count, 3)
        for row in report['roles'].values():
            self.assertFalse(row['verified_this_run'])
            self.assertEqual(row['verification_write'], 'pending')
            self.assertIn('not confirmed', row['verification_error'])

    def test_compact_keeps_judgment_evidence_and_does_not_shrink_disk_record(self):
        path, run = self.start()
        run['roles']['arbiter']['evidence'] = {'agent_message': 'A, because paths move.',
            'execution': {'returncode': 0}, 'observed_models': [], 'commands': [],
            'usage': {'input_tokens': 12345}}
        partner_tryout.save(path, run)
        before = path.read_bytes()
        compact = partner_tryout.compact_output(path, run)
        self.assertEqual(compact['roles']['deep_reasoner']['native_agent'], run['roles']['deep_reasoner']['native_agent'])
        self.assertEqual(compact['roles']['arbiter']['evidence']['agent_message'], 'A, because paths move.')
        self.assertEqual(compact['roles']['arbiter']['evidence']['observed_models'], [])
        self.assertNotIn('usage', compact['roles']['arbiter']['evidence'])
        self.assertEqual(compact['roles']['arbiter']['evidence_file'], str(path.resolve()))
        self.assertEqual(path.read_bytes(), before)

    def test_collect_only_waits_for_unfinished_jobs_on_next_call(self):
        path, _ = self.start()
        evidence = {'agent_message': SORTED, 'execution': {'returncode': 0}}
        def first(args, **kwargs):
            return json.dumps({'jobs': [
                {'job_id': 'job-fast_worker', 'state': 'DONE', 'result': evidence},
                {'job_id': 'job-arbiter', 'state': 'RUNNING'}]})
        with patch.object(partner_tryout, 'delegate', side_effect=first):
            partner_tryout.collect(path, 60, {})
        with patch.object(partner_tryout, 'delegate', side_effect=self.batch) as call:
            report = partner_tryout.collect(path, 60, {})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0][1:2], ['job-arbiter'])
        self.assertNotIn('job-fast_worker', call.call_args.args[0])
        self.assertTrue(report['roles']['fast_worker']['passed'])

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
