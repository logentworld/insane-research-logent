import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "skills" / "insane-research-main" / "scripts" / "orchestrator.py"


class InsaneResearchOrchestratorTest(unittest.TestCase):
    def test_init_status_and_list_create_a_ledger_session(self):
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp) / "RESEARCH"
            init = subprocess.run(
                [sys.executable, str(SCRIPT), "init", "--topic", "AI 연구", "--base", str(base)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            started = json.loads(init.stdout)
            session_id = started["session_id"]
            state_path = base / session_id / "state.json"
            self.assertTrue(state_path.is_file())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(2, state["ledger_schema"])
            self.assertEqual(session_id, state["session_id"])

            status = subprocess.run(
                [sys.executable, str(SCRIPT), "status", "--session", session_id, "--base", str(base)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(session_id, json.loads(status.stdout)["session_id"])

            listing = subprocess.run(
                [sys.executable, str(SCRIPT), "list", "--base", str(base)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(listing.returncode, 0, listing.stderr)
            sessions = json.loads(listing.stdout)["sessions"]
            self.assertEqual([session_id], [item["session_id"] for item in sessions])


if __name__ == "__main__":
    unittest.main()
