from __future__ import annotations

import importlib.util
import json
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
