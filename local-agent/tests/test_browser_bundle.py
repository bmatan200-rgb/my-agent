"""Validate the production page's browser JavaScript without launching the browser."""
import ast
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "agent.py"


class BrowserBundleTests(unittest.TestCase):
    def test_embedded_browser_script_syntax(self):
        if not shutil.which("node"):
            self.skipTest("Node.js not installed")
        tree = ast.parse(AGENT.read_text(encoding="utf-8"))
        page_assignment = next(
            n for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PAGE" for t in n.targets)
        )
        page = ast.literal_eval(page_assignment.value)
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        self.assertIsNotNone(script)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "agent-ui.js"
            target.write_text(script.group(1), encoding="utf-8")
            check = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()