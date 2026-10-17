import copy
import json
import tempfile
import unittest
from collections import deque
from pathlib import Path

from astra.config import DEFAULT, AstraError, load_config, validate_config
from astra.context import collect_context
from astra.engine import Pipeline, build_messages, check_answer, new_state, run_lock


PLAN = json.dumps({"goal": "Answer", "steps": ["Calculate"], "acceptance": ["Correct number"]})
PASS = json.dumps({"verdict": "pass", "issues": []})
REVISE = json.dumps({"verdict": "revise", "issues": ["Wrong number; calculate again"]})
UNCERTAIN = json.dumps({"verdict": "uncertain", "issues": ["Cannot establish this fact"]})


class ScriptedClient:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.messages = []

    def complete(self, role, messages, max_tokens, schema, timeout):
        self.messages.append(messages)
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, dict):
            return response
        return {"text": response, "truncated": False, "input_tokens": 20, "output_tokens": 10, "estimated_cost_usd": 0.0}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = copy.deepcopy(DEFAULT)

    def pipeline(self, responses, mode="balanced", checks=None, context=None):
        state = new_state("Calculate 17 times 23", self.config, mode, context or {"documents": [], "excerpts": []}, checks or {"contains": ["391"]})
        return Pipeline.create(self.root, state, client=ScriptedClient(responses))

    def test_failed_acceptance_overrides_model_pass_and_rechecks_revision(self):
        pipeline = self.pipeline([PLAN, "390", PASS, "391", PASS])
        state = pipeline.run()
        self.assertEqual(state["status"], "model_review_passed")
        self.assertEqual([call["phase"] for call in state["calls"]], ["planner", "draft", "review", "revise", "review"])
        self.assertEqual(state["answer"], "391")
        self.assertIn("failed_checks", pipeline.client.messages[3][1]["content"])
        repair_input = json.loads(pipeline.client.messages[3][1]["content"])
        self.assertEqual(repair_input["review"]["verdict"], "revise")
        self.assertIn("Failed machine check", repair_input["review"]["issues"][0])

    def test_review_of_old_draft_cannot_approve_unreviewed_revision(self):
        pipeline = self.pipeline([PLAN, "wrong", REVISE, "391", UNCERTAIN])
        state = pipeline.run()
        self.assertEqual(state["status"], "needs_review")
        self.assertEqual(state["review"]["verdict"], "uncertain")

    def test_budget_counts_malformed_json_and_resume_keeps_old_calls(self):
        self.config["limits"]["max_calls"] = 2
        pipeline = self.pipeline(["not JSON", PLAN])
        state = pipeline.run()
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertEqual(state["phase"], "draft")
        restored = Pipeline.load(pipeline.directory, client=ScriptedClient(["391", PASS]))
        restored.state["config"]["limits"]["max_calls"] = 4
        restored.run()
        self.assertEqual(len(restored.state["calls"]), 4)
        self.assertEqual(restored.state["status"], "model_review_passed")

    def test_network_failure_does_not_retry_automatically(self):
        pipeline = self.pipeline([AstraError("network failure")])
        self.assertEqual(pipeline.run()["status"], "failed")
        self.assertEqual(len(pipeline.state["calls"]), 1)
        self.assertIn("Chưa biết", (pipeline.directory / "report.md").read_text())

    def test_interruption_can_resume_without_repeating_successful_plan(self):
        pipeline = self.pipeline([PLAN, KeyboardInterrupt()])
        self.assertEqual(pipeline.run()["status"], "interrupted")
        restored = Pipeline.load(pipeline.directory, client=ScriptedClient(["391", PASS]))
        restored.run()
        self.assertEqual(restored.state["status"], "model_review_passed")
        self.assertEqual([call["role"] for call in restored.state["calls"]].count("planner"), 1)

    def test_fast_mode_still_reviews_but_never_repairs(self):
        pipeline = self.pipeline(["390", REVISE], mode="fast")
        state = pipeline.run()
        self.assertEqual(state["status"], "needs_review")
        self.assertEqual(len(state["calls"]), 2)

    def test_truncated_answer_cannot_pass(self):
        truncated = {"text": "391", "truncated": True, "input_tokens": 10, "output_tokens": 10, "estimated_cost_usd": 0.0}
        pipeline = self.pipeline([truncated, PASS], mode="fast")
        self.assertEqual(pipeline.run()["status"], "needs_review")

    def test_hallucinated_source_fails_check(self):
        results = check_answer("391 [S99]", {}, {"excerpts": []})
        self.assertFalse(all(result["passed"] for result in results))

    def test_source_omitted_from_reviewer_cannot_receive_pass(self):
        context = {"documents": [], "excerpts": [{"id": "S1", "text": "X" * 4000}]}
        pipeline = self.pipeline(["391 [S1]", PASS], mode="fast", context=context)
        state = pipeline.run()
        self.assertEqual(state["status"], "needs_review")
        self.assertIn("S1", state["calls"][-1]["omitted"])

    def test_original_task_is_not_silently_truncated(self):
        pipeline = self.pipeline([])
        pipeline.state["task"] = "A" * 8000
        with self.assertRaisesRegex(AstraError, "ngân sách ngữ cảnh"):
            build_messages(pipeline.state, "worker")

    def test_closed_run_does_not_spend_more_calls(self):
        pipeline = self.pipeline(["391", PASS], mode="fast")
        pipeline.run()
        restored = Pipeline.load(pipeline.directory, client=ScriptedClient([]))
        restored.run()
        self.assertEqual(len(restored.state["calls"]), 2)

    def test_run_lock_rejects_concurrent_writer(self):
        pipeline = self.pipeline([])
        with run_lock(pipeline.directory):
            with self.assertRaises(AstraError):
                pipeline.run()

    def test_resume_rejects_stale_checkpoint_instead_of_repeating_work(self):
        pipeline = self.pipeline(["391", PASS], mode="fast")
        restored = Pipeline.load(pipeline.directory, client=ScriptedClient([]))
        pipeline.run()
        with self.assertRaisesRegex(AstraError, "Checkpoint đã đổi"):
            restored.run()

    def test_revision_without_remaining_review_budget_does_not_keep_old_review(self):
        self.config["limits"]["max_calls"] = 4
        pipeline = self.pipeline([PLAN, "390", REVISE, "391"])
        state = pipeline.run()
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertIsNone(state["review"])
        self.assertEqual(state["phase"], "review")

    def test_private_state_permissions(self):
        pipeline = self.pipeline(["391", PASS], mode="fast")
        pipeline.run()
        self.assertEqual(pipeline.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((pipeline.directory / "state.json").stat().st_mode & 0o777, 0o600)

    def test_unknown_limit_typo_is_rejected(self):
        config = self.root / "config.json"
        config.write_text('{"limits":{"max_call":10}}')
        with self.assertRaises(AstraError):
            load_config(config)

    def test_credentials_in_url_are_rejected(self):
        self.config["providers"]["local"]["base_url"] = "http://secret:password@localhost:11434"
        with self.assertRaises(AstraError):
            validate_config(self.config)

    def test_raw_api_key_in_config_is_rejected_before_checkpoint(self):
        self.config["providers"]["local"]["api_key"] = "test-placeholder"
        with self.assertRaises(AstraError):
            validate_config(self.config)

    def test_retrieval_is_bounded_and_records_source_hash(self):
        file = self.root / "source.md"
        file.write_text("irrelevant " * 200 + "\nCPU i5-7200U RAM 8 GB\n", encoding="utf-8")
        context = collect_context("CPU RAM", [str(file)], 800)
        self.assertIn("CPU", context["excerpts"][0]["text"])
        self.assertLessEqual(sum(len(item["text"].encode()) for item in context["excerpts"]), 800)
        self.assertEqual(len(context["documents"][0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
