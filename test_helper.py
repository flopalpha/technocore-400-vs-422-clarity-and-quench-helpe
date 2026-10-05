"""Runnable tests for helper.py. Offline only, uses tempfile for files."""
import json
import tempfile
import unittest
import helper
import cli


class TestNormalize(unittest.TestCase):
    def test_lower_and_collapse(self):
        self.assertEqual(helper.normalize_text("Hello   WORLD"), "hello world")

    def test_strip(self):
        self.assertEqual(helper.normalize_text("  a b  "), "a b")

    def test_empty(self):
        self.assertEqual(helper.normalize_text("   "), "")

    def test_type_error(self):
        with self.assertRaises(TypeError):
            helper.normalize_text(123)

    def test_hash_stable(self):
        a = helper.hash_text("hello")
        b = helper.hash_text("hello")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)


class TestPreview(unittest.TestCase):
    def test_match(self):
        r = helper.preview_normalization("Hello World", "hello   world")
        self.assertTrue(r["match"])
        self.assertIn("heuristic_only", r)

    def test_suffix_only_flag(self):
        r = helper.preview_normalization("post heartbeats", "post heartbeats now")
        self.assertFalse(r["match"])
        self.assertTrue(r["trailing_diff"]["only_suffix_changed"])

    def test_different(self):
        r = helper.preview_normalization("alpha beta", "gamma delta epsilon")
        self.assertFalse(r["match"])

    def test_trailing_diff_common(self):
        d = helper.trailing_token_diff("a b c", "a b c d")
        self.assertEqual(d["common_prefix_len"], 3)
        self.assertEqual(d["added_tokens"], ["d"])


class TestInterpret(unittest.TestCase):
    def test_400_is_ceiling(self):
        r = helper.interpret_status(400, "invariant ceiling")
        self.assertEqual(r["category"], "ceiling_400")
        self.assertFalse(r["should_retry_same_payload"])

    def test_422_is_duplicate(self):
        r = helper.interpret_status(422, "repeated normalized text")
        self.assertEqual(r["category"], "duplicate_filter_422")
        self.assertFalse(r["should_retry_same_payload"])
        self.assertTrue(any("Rephrase" in s or "rephrase" in s.lower() for s in r["safe_next_steps"]))

    def test_success(self):
        r = helper.interpret_status(200, "ok")
        self.assertEqual(r["category"], "success")

    def test_unknown(self):
        r = helper.interpret_status(418, "teapot")
        self.assertEqual(r["category"], "unknown")

    def test_429(self):
        r = helper.interpret_status(429, "slow down")
        self.assertEqual(r["category"], "rate_limit_429")


class TestParseAndQuench(unittest.TestCase):
    def test_parse_lines(self):
        lines = ["seq 1 status 422 duplicate", "seq 2 status 400 ceiling", "no code here"]
        out = helper.parse_log_lines(lines)
        self.assertEqual(out[0]["status"], 422)
        self.assertEqual(out[1]["status"], 400)
        self.assertIsNone(out[2]["status"])

    def test_quench_422_streak(self):
        r = helper.plan_quench([422, 422, 422])
        self.assertEqual(r["action"], "stop_and_rephrase")
        self.assertTrue(r["rephrase_required"])

    def test_quench_400_streak(self):
        r = helper.plan_quench([400, 400])
        self.assertEqual(r["action"], "stop")

    def test_quench_single_422(self):
        r = helper.plan_quench([422])
        self.assertEqual(r["action"], "rephrase_before_retry")

    def test_quench_empty(self):
        r = helper.plan_quench([])
        self.assertEqual(r["action"], "no_data")

    def test_quench_mixed_tail(self):
        r = helper.plan_quench([422, 422, 400, 400])
        self.assertEqual(r["consecutive_400_tail"], 2)
        self.assertEqual(r["action"], "stop")

    def test_quench_from_dicts(self):
        r = helper.plan_quench([{"status": 422}, {"status": 422}])
        self.assertEqual(r["total_422"], 2)


class TestAuditAndGap(unittest.TestCase):
    def test_audit_redacted(self):
        bundle = helper.build_audit_bundle(
            [{"payload": "secret hello", "status": 422, "seq": 15227305}],
            room="technocore",
        )
        text = helper.bundle_to_json(bundle)
        self.assertNotIn("secret hello", text)
        self.assertIn("payload_hash_short", text)
        self.assertEqual(bundle["count"], 1)

    def test_audit_bundle_file_roundtrip(self):
        bundle = helper.build_audit_bundle(
            [{"payload": "hello world", "status": 400, "seq": 1, "message": "ceiling"}]
        )
        text = helper.bundle_to_json(bundle)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(text)
            name = f.name
        with open(name, "r") as fh:
            loaded = json.load(fh)
        self.assertEqual(loaded["count"], 1)
        self.assertEqual(loaded["items"][0]["status"], 400)

    def test_gap_report_file(self):
        report = helper.docs_gap_report(["suffix still flagged"], room="technocore")
        self.assertIn("Observed", report)
        self.assertIn("Questions for ops", report)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(report)
            name = f.name
        with open(name, "r") as fh:
            back = fh.read()
        self.assertIn("suffix still flagged", back)

    def test_gap_empty(self):
        report = helper.docs_gap_report([])
        self.assertIn("no observations", report)


class TestCliHelpers(unittest.TestCase):
    def test_parse_status_list(self):
        self.assertEqual(cli.parse_status_list("422,422,400"), [422, 422, 400])
        self.assertEqual(cli.parse_status_list(""), [])

    def test_cli_parser_builds(self):
        p = cli.build_parser()
        args = p.parse_args(["interpret", "--status", "422"])
        self.assertEqual(args.status, 422)


if __name__ == "__main__":
    unittest.main()
