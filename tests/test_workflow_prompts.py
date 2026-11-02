import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('workflow_prompts',
    Path(__file__).resolve().parents[1] / 'scripts/run-test-prompts.py')
prompts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompts)


class WorkflowPromptTests(unittest.TestCase):
    def test_inline_task_does_not_require_a_collaboration_receipt(self):
        entry = {'id': 'inline', 'prompt': 'fix one typo', 'should_trigger': True,
                 'requires_receipt': False}
        with patch.object(prompts.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, 'Fixed; diff checked.', '')):
            self.assertEqual(prompts.live_check([entry], 'agent'), [])

    def test_no_receipt_is_not_evidence_of_success_when_agent_failed(self):
        entry = {'id': 'inline', 'prompt': 'fix one typo', 'should_trigger': True,
                 'requires_receipt': False}
        with patch.object(prompts.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 1, '', '')):
            self.assertEqual(prompts.live_check([entry], 'agent'), ['inline: agent command exited 1'])
