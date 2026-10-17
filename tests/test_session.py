import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from astra.cli import main
from astra.config import DEFAULT, AstraError
from astra.engine import Pipeline, build_messages, new_state
from astra.prompts import protocol_bundle
from astra.session import add_note, create_session, memory_payload, read_session, record_run, snapshot
from test_workflow import PASS, PLAN, ScriptedClient


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = copy.deepcopy(DEFAULT)
        self.directory = create_session("demo", "Keep the same project goal", ["Use local models"], self.config, protocol_bundle(), "balanced", self.root)

    def state(self):
        data = read_session(self.directory)
        return new_state("Return 391", data["config"], data["mode"], {"documents": [], "excerpts": []}, {},
                         snapshot(data, self.directory), data["protocol"])

    def test_contract_reaches_every_role_and_repair_unchanged(self):
        state = self.state()
        state.update({"answer": "391", "review": {"verdict": "revise", "issues": ["Check"]}})
        for role, revision in (("planner", False), ("worker", False), ("reviewer", False), ("worker", True)):
            messages, _, _, _ = build_messages(state, role, revision)
            body = json.loads(messages[1]["content"])
            self.assertEqual(body["session_memory"]["contract"], state["session"]["contract"])

    def test_note_is_visible_to_next_run_but_not_to_existing_snapshot(self):
        existing = self.state()
        add_note("demo", "decision", "Use SQLite", root=self.root)
        current = self.state()
        self.assertEqual(existing["session"]["notes"], [])
        self.assertEqual(current["session"]["notes"][0]["text"], "Use SQLite")

    def test_prompt_update_does_not_change_existing_session_or_resume(self):
        state = self.state()
        original = build_messages(state, "planner")[0]
        pipeline = Pipeline.create(self.root / "runs", state, client=ScriptedClient([]))
        with patch("astra.engine.protocol_bundle", return_value={"planner": "CHANGED"}):
            restored = Pipeline.load(pipeline.directory, client=ScriptedClient([]))
            self.assertEqual(build_messages(restored.state, "planner")[0], original)

    def test_goal_edits_are_detected_before_network(self):
        state = self.state()
        state["session"]["contract"]["goal"] = "Different goal"
        pipeline = Pipeline.create(self.root / "runs", state, client=ScriptedClient([]))
        self.assertEqual(pipeline.run()["status"], "failed")
        self.assertEqual(pipeline.state["calls"], [])

    def test_model_or_mode_changes_are_rejected(self):
        for field in ("model", "mode"):
            state = self.state()
            if field == "model":
                state["config"]["roles"]["worker"]["model"] = "different-model"
            else:
                state["mode"] = "fast"
            with self.assertRaises(AstraError):
                build_messages(state, "worker")

    def test_protocol_corruption_is_detected(self):
        state = self.state()
        state["protocol"]["worker"] = "Different instructions"
        with self.assertRaises(AstraError):
            build_messages(state, "worker")

    def test_memory_overflow_fails_instead_of_dropping_decisions(self):
        for index in range(12):
            add_note("demo", "decision", f"Decision {index}: " + "A" * 300, root=self.root)
        with self.assertRaisesRegex(AstraError, "ngân sách ngữ cảnh"):
            build_messages(self.state(), "worker")

    def test_optional_notes_can_be_omitted_without_dropping_contract(self):
        for index in range(12):
            add_note("demo", "open", f"Question {index}: " + "A" * 300, root=self.root)
        state = self.state()
        messages, _, _, omitted = build_messages(state, "worker")
        self.assertTrue(any(item.startswith("note:") for item in omitted))
        self.assertEqual(json.loads(messages[1]["content"])["session_memory"]["contract"], state["session"]["contract"])

    def test_fact_needs_source_and_superseding_preserves_history(self):
        with self.assertRaises(AstraError):
            add_note("demo", "fact", "RAM 8 GB", root=self.root)
        first = add_note("demo", "fact", "RAM 8 GB", "hardware check", root=self.root)
        second = add_note("demo", "fact", "RAM 16 GB", "new hardware check", first, self.root)
        data = read_session(self.directory)
        self.assertFalse(data["notes"][0]["active"])
        self.assertEqual(data["notes"][1]["supersedes"], first)
        self.assertEqual([note["id"] for note in snapshot(data, self.directory)["notes"]], [second])

    def test_recorded_outputs_stay_unverified_and_handoff_is_private(self):
        pipeline = Pipeline.create(self.root / "runs", self.state(), client=ScriptedClient([PLAN, "391", PASS]))
        pipeline.run()
        record_run(pipeline.state, pipeline.directory)
        data = read_session(self.directory)
        self.assertEqual(data["notes"], [])
        self.assertEqual(data["runs"][0]["answer_preview"], "391")
        self.assertIn(str(pipeline.directory), (self.directory / "HANDOFF.md").read_text())
        self.assertEqual((self.directory / "HANDOFF.md").stat().st_mode & 0o777, 0o600)
        revision = data["revision"]
        record_run(pipeline.state, pipeline.directory)
        self.assertEqual(read_session(self.directory)["revision"], revision)

    def test_recent_answer_is_bounded_and_labelled_as_preview(self):
        state = self.state()
        state["answer"] = "Dữ liệu " * 300
        state["status"] = "needs_review"
        record_run(state, self.root / "run")
        memory = snapshot(read_session(self.directory), self.directory)
        _, _, recent = memory_payload(memory)
        self.assertTrue(recent[0]["preview_truncated"])
        self.assertLessEqual(len(recent[0]["answer_preview"].encode()), 600)

    def test_cli_cannot_override_session_model(self):
        result = main(["run", "hello", "--session", "demo", "--sessions-dir", str(self.root), "--model", "other"])
        self.assertEqual(result, 1)

    def test_session_names_cannot_escape_root(self):
        with self.assertRaises(AstraError):
            create_session("../outside", "Goal", [], self.config, protocol_bundle(), "fast", self.root)

    def test_legacy_run_warns_that_original_prompt_is_not_preserved(self):
        state = new_state("Test", self.config, "fast", {"documents": [], "excerpts": []}, {})
        state.pop("protocol")
        state.pop("protocol_hash")
        pipeline = Pipeline.create(self.root / "runs", state, client=ScriptedClient([]))
        restored = Pipeline.load(pipeline.directory, client=ScriptedClient([]))
        self.assertIn("legacy_protocol_warning", restored.state)


if __name__ == "__main__":
    unittest.main()
